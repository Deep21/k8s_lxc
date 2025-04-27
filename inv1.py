#!/usr/bin/env python3

import subprocess
import json
import os
import yaml
import sys

# Chemin vers la clé SSH privée
SSH_KEY_PATH = "/root/.ssh/k8s_lxd_key"
# Répertoire contenant les fichiers manifest
MANIFEST_DIR = "./data"

def list_cluster_names_from_manifests():
    """Lit tous les fichiers manifest YAML et extrait les noms des clusters"""
    cluster_names = []
    try:
        files = [f for f in os.listdir(MANIFEST_DIR) if f.endswith('.yaml') or f.endswith('.yml')]
    except FileNotFoundError:
        print(f"Répertoire introuvable: {MANIFEST_DIR}", file=sys.stderr)
        return []
    
    for file in files:
        path = os.path.join(MANIFEST_DIR, file)
        try:
            with open(path, 'r') as f:
                manifest = yaml.safe_load(f)
                if manifest and 'metadata' in manifest and 'cluster_name' in manifest['metadata']:
                    cluster_names.append(manifest['metadata']['cluster_name'])
        except Exception as e:
            print(f"Erreur lors de la lecture du fichier {file}: {e}", file=sys.stderr)
            continue
    
    return cluster_names

def get_lxc_containers(cluster_name):
    """Récupère les conteneurs LXC pour un cluster spécifique"""
    try:
        # Exécute la commande lxc list avec un filtre sur le nom du cluster
        result = subprocess.run(["lxc", "list", f"{cluster_name}-", "--format", "json"], 
                               capture_output=True, text=True, check=True)
        containers = json.loads(result.stdout)
        
        # Prépare la structure de l'inventaire Ansible pour ce cluster
        inventory = {
            "_meta": {"hostvars": {}},
            "masters": {"hosts": []},
            "workers": {"hosts": []}
        }
        
        # Parcourt chaque conteneur pour extraire les informations nécessaires
        for container in containers:
            name = container.get("name")
            status = container.get("status")
            
            # Ne traite que les conteneurs en cours d'exécution
            if status == "Running":
                # Récupère UNIQUEMENT l'adresse IP de l'interface eth0
                ip_address = None
                network_info = container.get("state", {}).get("network", {}).get("eth0", {})
                
                if network_info:
                    for address in network_info.get("addresses", []):
                        if address.get("family") == "inet":  # IPv4
                            ip_address = address.get("address")
                            break
                
                if ip_address:
                    # Classification master/worker par nom
                    if f"{cluster_name}-master" in name:
                        inventory["masters"]["hosts"].append(name)
                    elif f"{cluster_name}-worker" in name:
                        inventory["workers"]["hosts"].append(name)
                    
                    # Configuration SSH
                    inventory["_meta"]["hostvars"][name] = {
                        "ansible_host": ip_address,
                        "ansible_user": "ubuntu",
                        "ansible_ssh_private_key_file": SSH_KEY_PATH,
                        "ansible_ssh_common_args": "-o StrictHostKeyChecking=no"
                    }
        
        return inventory
    
    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de l'exécution de la commande lxc pour {cluster_name}: {e}", file=sys.stderr)
        return {"_meta": {"hostvars": {}}, "masters": {"hosts": []}, "workers": {"hosts": []}}
    except json.JSONDecodeError as e:
        print(f"Erreur lors du décodage JSON pour {cluster_name}: {e}", file=sys.stderr)
        return {"_meta": {"hostvars": {}}, "masters": {"hosts": []}, "workers": {"hosts": []}}
    except Exception as e:
        print(f"Erreur inattendue pour {cluster_name}: {e}", file=sys.stderr)
        return {"_meta": {"hostvars": {}}, "masters": {"hosts": []}, "workers": {"hosts": []}}

def get_combined_inventory():
    """Combine les inventaires de tous les clusters"""
    # Récupère tous les noms de clusters
    cluster_names = list_cluster_names_from_manifests()
    
    if not cluster_names:
        print("Aucun cluster trouvé dans les manifests", file=sys.stderr)
        return {"_meta": {"hostvars": {}}}
    
    # Prépare l'inventaire combiné
    combined_inventory = {
        "_meta": {"hostvars": {}},
        "all": {"children": ["masters", "workers"]},
        "masters": {"hosts": []},
        "workers": {"hosts": []}
    }
    
    # Boucle sur chaque cluster et ajoute ses hôtes à l'inventaire combiné
    for cluster_name in cluster_names:
        inventory = get_lxc_containers(cluster_name)
        
        # Ajoute les hôtes masters
        combined_inventory["masters"]["hosts"].extend(inventory.get("masters", {}).get("hosts", []))
        
        # Ajoute les hôtes workers
        combined_inventory["workers"]["hosts"].extend(inventory.get("workers", {}).get("hosts", []))
        
        # Ajoute les variables d'hôtes
        combined_inventory["_meta"]["hostvars"].update(inventory.get("_meta", {}).get("hostvars", {}))
    
    return combined_inventory

def parse_args():
    """Parse les arguments de ligne de commande"""
    # Ansible appelle le script avec --list ou --host 
    if len(sys.argv) > 1:
        if sys.argv == '--list':
            return get_combined_inventory()
        elif sys.argv == '--host' and len(sys.argv) > 2:
            # Retourne un dictionnaire vide car toutes les variables d'hôte sont déjà dans _meta
            return {}
    
    # Si aucun argument valide n'est fourni, retourne l'inventaire complet
    return get_combined_inventory()

if __name__ == "__main__":
    inventory = parse_args()
    print(json.dumps(inventory, indent=2))
