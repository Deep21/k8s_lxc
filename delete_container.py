#!/usr/bin/env python3
import subprocess
import sys
import time
import os
import json
import shutil
import glob
import signal
from pathlib import Path

# Chemins complets vers les exécutables
LXC_BIN = "/snap/bin/lxc"
SYSTEMCTL_BIN = "/bin/systemctl"

def run_command(cmd, timeout=60):
    """Exécute une commande avec gestion du timeout et des erreurs"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout)
        if result.returncode != 0:
            return (False, result.stderr.strip())
        return (True, result.stdout.strip())
    except subprocess.TimeoutExpired:
        return (False, f"Timeout après {timeout} secondes")
    except Exception as e:
        return (False, str(e))

def get_all_containers():
    """Récupère tous les conteneurs LXD"""
    success, output = run_command([LXC_BIN, "list", "--format", "json"])
    if not success:
        print(f"Erreur lors de la récupération des conteneurs: {output}", file=sys.stderr)
        return []
    
    try:
        containers = json.loads(output)
        return [c["name"] for c in containers]
    except Exception as e:
        print(f"Erreur JSON: {str(e)}", file=sys.stderr)
        return []

def get_container_info(name):
    """Récupère les informations détaillées sur un conteneur"""
    success, output = run_command([LXC_BIN, "info", name, "--format", "json"])
    if not success:
        return None
    
    try:
        return json.loads(output)
    except Exception:
        return None

def kill_container_processes(name):
    """Tue tous les processus associés au conteneur"""
    print(f"Recherche et arrêt des processus pour {name}...")
    
    # Trouver le PID du conteneur
    success, output = run_command(["ps", "aux"])
    if not success:
        return
    
    for line in output.splitlines():
        if name in line and "lxc" in line:
            try:
                pid = int(line.split()[1])
                print(f"Arrêt du processus {pid} pour {name}...")
                os.kill(pid, signal.SIGKILL)
            except (ValueError, ProcessLookupError, PermissionError) as e:
                print(f"Erreur lors de l'arrêt du processus: {e}")

def stop_container(name, timeout=60):
    """Arrête un conteneur avec plusieurs méthodes si nécessaire"""
    print(f"Arrêt du conteneur {name}...")
    
    # Méthode 1: Arrêt normal
    success, output = run_command([LXC_BIN, "stop", name, "--timeout", str(timeout)])
    if success:
        return True
    
    print(f"Échec de l'arrêt normal pour {name}, tentative avec --force...")
    
    # Méthode 2: Arrêt forcé
    success, output = run_command([LXC_BIN, "stop", name, "--force", "--timeout", str(timeout)])
    if success:
        return True
    
    # Méthode 3: Tuer les processus
    kill_container_processes(name)
    
    # Vérifier si le conteneur est arrêté
    time.sleep(2)
    info = get_container_info(name)
    if info and info.get("status") == "Stopped":
        return True
    
    print(f"Impossible d'arrêter le conteneur {name} après plusieurs tentatives", file=sys.stderr)
    return False

def delete_container(name):
    """Supprime un conteneur avec plusieurs tentatives"""
    print(f"Suppression du conteneur {name}...")
    
    # Première tentative: suppression normale
    success, output = run_command([LXC_BIN, "delete", name])
    if success:
        return True
    
    print(f"Échec de la suppression normale pour {name}, tentative avec --force...")
    
    # Deuxième tentative: suppression forcée
    success, output = run_command([LXC_BIN, "delete", name, "--force"])
    if success:
        return True
    
    print(f"Échec de la suppression forcée pour {name}: {output}", file=sys.stderr)
    return False

def cleanup_cgroups(name):
    """Nettoie les cgroups associés au conteneur"""
    cgroup_paths = [
        f"/sys/fs/cgroup/systemd/lxc/{name}",
        f"/sys/fs/cgroup/systemd/lxc/{name}.scope",
        f"/sys/fs/cgroup/unified/lxc.payload.{name}"
    ]
    
    for base_path in ["/sys/fs/cgroup", "/sys/fs/cgroup/unified"]:
        if os.path.exists(base_path):
            for root, dirs, _ in os.walk(base_path):
                for d in dirs:
                    if name in d:
                        cgroup_paths.append(os.path.join(root, d))
    
    for path in cgroup_paths:
        if os.path.exists(path):
            try:
                print(f"Suppression du cgroup {path}...")
                shutil.rmtree(path, ignore_errors=True)
            except Exception as e:
                print(f"Erreur lors de la suppression du cgroup {path}: {str(e)}", file=sys.stderr)

def cleanup_storage_volumes(name):
    """Nettoie les volumes de stockage associés au conteneur"""
    # Récupérer tous les pools de stockage
    success, output = run_command([LXC_BIN, "storage", "list", "--format", "json"])
    if not success:
        print(f"Erreur lors de la récupération des pools de stockage: {output}", file=sys.stderr)
        return
    
    try:
        pools = json.loads(output)
        for pool in pools:
            pool_name = pool.get("name")
            if not pool_name:
                continue
            
            # Récupérer les volumes dans ce pool
            success, output = run_command([LXC_BIN, "storage", "volume", "list", pool_name, "--format", "json"])
            if not success:
                continue
            
            try:
                volumes = json.loads(output)
                for vol in volumes:
                    vol_name = vol.get("name", "")
                    vol_type = vol.get("type", "")
                    
                    # Supprimer les volumes associés au conteneur
                    if (vol_name == name or 
                        vol_name.startswith(f"{name}/") or 
                        vol_name.endswith(f"_{name}") or
                        name in vol_name):
                        print(f"Suppression du volume {vol_name} ({vol_type}) du pool {pool_name}...")
                        run_command([LXC_BIN, "storage", "volume", "delete", pool_name, f"{vol_type}/{vol_name}", "--force"])
            except Exception as e:
                print(f"Erreur lors du traitement des volumes du pool {pool_name}: {str(e)}", file=sys.stderr)
    except Exception as e:
        print(f"Erreur lors du traitement des pools de stockage: {str(e)}", file=sys.stderr)

def cleanup_lxd_db(name):
    """Tente de nettoyer les références dans la base de données LXD"""
    # Cette fonction est risquée et ne doit être utilisée qu'en dernier recours
    lxd_db_path = "/var/snap/lxd/common/lxd/database/local.db"
    if not os.path.exists(lxd_db_path):
        return
    
    print(f"ATTENTION: Tentative de nettoyage de la base de données LXD pour {name}...")
    print("Cette opération est risquée et peut causer des problèmes si elle échoue.")
    
    # Sauvegarde de la base de données
    backup_path = f"/tmp/lxd_db_backup_{int(time.time())}.db"
    shutil.copy2(lxd_db_path, backup_path)
    print(f"Sauvegarde de la base de données créée: {backup_path}")
    
    # Redémarrer LXD est plus sûr que de modifier directement la base de données
    print("Redémarrage du service LXD...")
    run_command([SYSTEMCTL_BIN, "restart", "snap.lxd.daemon"])
    time.sleep(5)

def cleanup_mounts(name):
    """Nettoie les points de montage associés au conteneur"""
    success, output = run_command(["mount"])
    if not success:
        return
    
    for line in output.splitlines():
        if name in line:
            mount_point = line.split(" on ")[1].split(" ")[0]
            print(f"Démontage de {mount_point}...")
            run_command(["umount", "-f", mount_point])

def cleanup_network_devices(name):
    """Nettoie les interfaces réseau associées au conteneur"""
    success, output = run_command(["ip", "link", "show"])
    if not success:
        return
    
    for line in output.splitlines():
        if name in line:
            parts = line.strip().split(":")
            if len(parts) >= 2:
                device = parts[1].strip()
                print(f"Suppression de l'interface réseau {device}...")
                run_command(["ip", "link", "delete", device])

def cleanup_lxd_leftovers(name):
    """Nettoie les fichiers résiduels de LXD"""
    paths_to_check = [
        f"/var/snap/lxd/common/lxd/containers/{name}",
        f"/var/snap/lxd/common/lxd/devices/{name}",
        f"/var/snap/lxd/common/lxd/snapshots/{name}",
        f"/var/snap/lxd/common/lxd/logs/{name}",
        f"/var/snap/lxd/common/lxd/storage-pools/*/containers/{name}"
    ]
    
    for path_pattern in paths_to_check:
        for path in glob.glob(path_pattern):
            if os.path.exists(path):
                print(f"Suppression du répertoire résiduel {path}...")
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                    else:
                        os.remove(path)
                except Exception as e:
                    print(f"Erreur lors de la suppression de {path}: {str(e)}", file=sys.stderr)

def cleanup_manifests(container_names, data_dir='./data'):
    """
    Supprime les fichiers yaml dans le répertoire data spécifié.
    Si 'all' est dans container_names, supprime tous les fichiers yaml.
    Sinon, supprime uniquement les fichiers yaml contenant le nom du cluster/conteneur.
    """
    print(f"Nettoyage des fichiers yaml dans {data_dir}...")
    data_path = Path(data_dir)

    # S'assurer que le répertoire data existe
    if not data_path.is_dir():
        print(f"Le répertoire de données '{data_dir}' n'existe pas. Nettoyage des manifests ignoré.", file=sys.stderr)
        return

    cleaned_count = 0
    if 'all' in container_names:
        # Supprimer tous les fichiers yaml
        yaml_files = list(data_path.glob('*.yaml'))
        if not yaml_files:
             print(f"Aucun fichier yaml trouvé dans {data_dir}.")
        for f_path in yaml_files:
            try:
                if f_path.is_file(): # S'assurer que c'est un fichier
                    print(f"Suppression du fichier yaml {f_path}")
                    f_path.unlink()
                    cleaned_count += 1
            except OSError as e:
                print(f"Erreur lors de la suppression du fichier yaml {f_path}: {e}", file=sys.stderr)
    else:
        # Supprimer les fichiers yaml correspondant aux noms des conteneurs/clusters
        found_any = False
        for name in container_names:
            # Recherche des fichiers contenant le nom exact du conteneur/cluster
            # Ajuster le pattern si nécessaire (ex: f"{name}.yaml", f"manifest-{name}-*.yaml")
            pattern = f'*{name}*.yaml'
            yaml_files = list(data_path.glob(pattern))

            if yaml_files:
                found_any = True
                for f_path in yaml_files:
                    try:
                        if f_path.is_file(): # S'assurer que c'est un fichier
                            print(f"Suppression du fichier yaml {f_path}")
                            f_path.unlink()
                            cleaned_count += 1
                    except OSError as e:
                        print(f"Erreur lors de la suppression du fichier yaml {f_path}: {e}", file=sys.stderr)
        if not found_any:
             print(f"Aucun fichier yaml correspondant aux noms fournis trouvé dans {data_dir}.")

    if cleaned_count > 0:
        print(f"{cleaned_count} fichier(s) yaml supprimé(s) de {data_dir}.")

def reload_lxd():
    """Recharge le service LXD"""
    print("Rechargement du service LXD...")
    run_command([SYSTEMCTL_BIN, "reload", "snap.lxd.daemon"])
    time.sleep(2)

def main():
    # Si un argument est donné, supprimer ce conteneur, sinon tous
    if len(sys.argv) > 1:
        if sys.argv[1] == "--help" or sys.argv[1] == "-h":
            print("Usage: python3 cleanup_lxd.py [nom_conteneur1 nom_conteneur2 ...]")
            print("Si aucun nom de conteneur n'est fourni, tous les conteneurs seront supprimés.")
            print("Utilisez 'all' comme argument pour supprimer tous les conteneurs et leurs manifests.")
            sys.exit(0)
        
        # Vérifier si 'all' est spécifié
        if 'all' in sys.argv[1:]:
            containers = get_all_containers()
            cleanup_all_manifests = True
        else:
            containers = sys.argv[1:]
            cleanup_all_manifests = False
    else:
        containers = get_all_containers()
        cleanup_all_manifests = True

    if not containers:
        print("Aucun conteneur à supprimer.")
        sys.exit(0)

    print(f"Suppression de {len(containers)} conteneur(s): {', '.join(containers)}")
    
    for c in containers:
        print(f"\n=== Traitement du conteneur {c} ===")
        
        # Étape 1: Arrêter le conteneur
        stop_container(c, timeout=30)
        
        # Étape 2: Nettoyer les montages
        cleanup_mounts(c)
        
        # Étape 3: Nettoyer les interfaces réseau
        cleanup_network_devices(c)
        
        # Étape 4: Supprimer le conteneur
        delete_container(c)
        
        # Étape 5: Nettoyer les cgroups
        cleanup_cgroups(c)
        
        # Étape 6: Nettoyer les volumes de stockage
        cleanup_storage_volumes(c)
        
        # Étape 7: Nettoyer les fichiers résiduels
        cleanup_lxd_leftovers(c)
    
    # Étape 8: Nettoyer les fichiers manifest
    if cleanup_all_manifests:
        cleanup_manifests(['all'])
    else:
        cleanup_manifests(containers)
    
    # Étape finale: Recharger LXD
    reload_lxd()
    
    print(f"\nSuppression terminée pour {len(containers)} conteneur(s).")
    print("Si vous rencontrez encore des problèmes, essayez de redémarrer le service LXD avec:")
    print("  sudo systemctl restart snap.lxd.daemon")

if __name__ == '__main__':
    if os.geteuid() != 0:
        print("Ce script doit être exécuté en tant que root (sudo).", file=sys.stderr)
        sys.exit(1)
    main()
