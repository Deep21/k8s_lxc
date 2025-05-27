#!/usr/bin/env python3

import yaml
import sys
import os
import argparse
import glob
import subprocess

def update_kubeconfig_all_names(kubeconfig_path, default_admin_user="kubernetes-admin"):
    """
    Met à jour les noms de cluster, contexte et utilisateur dans un fichier kubeconfig.
    - Cluster et Contexte prennent le nom du fichier (sans 'config-' et sans extension).
    - L'utilisateur (par défaut 'kubernetes-admin') est renommé en 'admin-<nom_fichier_base>'.
    Enregistre les modifications.
    """
    print(f"\n--- Traitement de : {kubeconfig_path} ---", flush=True)

    # 1. Déterminer le nom de base cible
    file_name_only = os.path.basename(kubeconfig_path)
    base_name_no_ext = os.path.splitext(file_name_only)[0]
    print(f"  Nom de fichier (sans extension) : '{base_name_no_ext}'", flush=True)

    target_base_name = base_name_no_ext
    if base_name_no_ext.startswith('config-'):
        target_base_name = base_name_no_ext[len('config-'):]
        print(f"  Préfixe 'config-' retiré. Nom de base cible : '{target_base_name}'", flush=True)
    else:
        print(f"  Aucun préfixe 'config-'. Nom de base cible : '{target_base_name}'", flush=True)

    # Déterminer le nouveau nom d'utilisateur
    new_user_name = f"admin-{target_base_name}"
    print(f"  Nouveau nom d'utilisateur cible : '{new_user_name}' (basé sur '{default_admin_user}')", flush=True)

    # 2. Charger le fichier kubeconfig
    try:
        with open(kubeconfig_path, 'r') as f:
            kubeconfig = yaml.safe_load(f)
        if kubeconfig is None:
            print(f"❌ ERREUR: Le fichier {kubeconfig_path} est vide ou n'est pas un YAML valide.", flush=True)
            return False
    except Exception as e:
        print(f"❌ ERREUR lors de la lecture de {kubeconfig_path}: {e}", flush=True)
        return False

    print("  Modification des noms...", flush=True)
    modified = False

    # 3. Modifier la section 'clusters'
    if 'clusters' in kubeconfig and isinstance(kubeconfig['clusters'], list):
        for i, cluster in enumerate(kubeconfig['clusters']):
            if isinstance(cluster, dict) and 'name' in cluster:
                old_cluster_name = cluster['name']
                cluster['name'] = target_base_name
                if old_cluster_name != target_base_name:
                    modified = True
                print(f"    Cluster[{i}]: nom changé de '{old_cluster_name}' à '{target_base_name}'", flush=True)
    else:
        print("    Avertissement: Section 'clusters' non trouvée ou format incorrect.", flush=True)

    # 4. Modifier la section 'users'
    user_renamed_in_users_section = False
    if 'users' in kubeconfig and isinstance(kubeconfig['users'], list):
        for i, user_entry in enumerate(kubeconfig['users']):
            if isinstance(user_entry, dict) and 'name' in user_entry:
                if user_entry['name'] == default_admin_user:
                    old_user_name_in_users = user_entry['name']
                    user_entry['name'] = new_user_name
                    if old_user_name_in_users != new_user_name:
                        modified = True
                        user_renamed_in_users_section = True
                    print(f"    Utilisateur[{i}] ('{default_admin_user}'): nom changé de '{old_user_name_in_users}' à '{new_user_name}'", flush=True)
                    break # On suppose une seule occurrence de l'admin par défaut
    if not user_renamed_in_users_section:
        print(f"    Avertissement: Utilisateur '{default_admin_user}' non trouvé dans la section 'users' ou format incorrect. Le nouveau nom '{new_user_name}' ne sera pas utilisé si l'utilisateur par défaut n'est pas trouvé.", flush=True)

    # 5. Modifier la section 'contexts'
    if 'contexts' in kubeconfig and isinstance(kubeconfig['contexts'], list):
        for i, context_entry in enumerate(kubeconfig['contexts']):
            if isinstance(context_entry, dict):
                # Renommer le contexte lui-même
                if 'name' in context_entry:
                    old_context_name = context_entry['name']
                    context_entry['name'] = target_base_name
                    if old_context_name != target_base_name:
                        modified = True
                    print(f"    Contexte[{i}]: nom changé de '{old_context_name}' à '{target_base_name}'", flush=True)

                # Mettre à jour les références dans le contexte
                if 'context' in context_entry and isinstance(context_entry['context'], dict):
                    # Mettre à jour la référence au cluster
                    if 'cluster' in context_entry['context']:
                        old_context_cluster_ref = context_entry['context']['cluster']
                        context_entry['context']['cluster'] = target_base_name
                        if old_context_cluster_ref != target_base_name:
                            modified = True
                        print(f"      Contexte[{i}].cluster (référence): changé de '{old_context_cluster_ref}' à '{target_base_name}'", flush=True)

                    # Mettre à jour la référence à l'utilisateur
                    if 'user' in context_entry['context']:
                        old_context_user_ref = context_entry['context']['user']
                        # On met à jour la référence seulement si l'utilisateur original était celui par défaut
                        if old_context_user_ref == default_admin_user:
                            context_entry['context']['user'] = new_user_name
                            if old_context_user_ref != new_user_name:
                                modified = True
                            print(f"      Contexte[{i}].user (référence): changé de '{old_context_user_ref}' à '{new_user_name}'", flush=True)
                        elif user_renamed_in_users_section and old_context_user_ref == new_user_name:
                            print(f"      Contexte[{i}].user (référence): déjà '{new_user_name}', pas de changement.", flush=True)
                        else:
                            print(f"      Contexte[{i}].user (référence): '{old_context_user_ref}' non changé (ne correspond pas à '{default_admin_user}' ou à '{new_user_name}' après renommage).", flush=True)
    else:
        print("    Avertissement: Section 'contexts' non trouvée ou format incorrect.", flush=True)

    # 6. Modifier le 'current-context'
    if 'current-context' in kubeconfig:
        old_current_context = kubeconfig['current-context']
        kubeconfig['current-context'] = target_base_name
        if old_current_context != target_base_name:
            modified = True
        print(f"    Current-context: changé de '{old_current_context}' à '{target_base_name}'", flush=True)
    else:
        print("    Avertissement: Champ 'current-context' non trouvé.", flush=True)

    if not modified:
        print("  Aucune modification de nom n'a été effectuée (les noms étaient peut-être déjà corrects ou la structure était inattendue).", flush=True)

    # 7. Sauvegarder le fichier modifié
    try:
        with open(kubeconfig_path, 'w') as f:
            yaml.dump(kubeconfig, f, default_flow_style=False)
        print(f"✅ Fichier {kubeconfig_path} enregistré avec succès.", flush=True)
        print(f"--- Fin du traitement pour : {kubeconfig_path} ---", flush=True)
        return True
    except Exception as e:
        print(f"❌ ERREUR lors de l'enregistrement de {kubeconfig_path}: {e}", flush=True)
        print(f"--- Fin du traitement (avec erreur) pour : {kubeconfig_path} ---", flush=True)
        return False

def scan_kubeconfig_directory(kubeconfig_dir="kubeconfig"):
    """
    Scanne le répertoire kubeconfig et retourne la liste des fichiers.
    """
    if not os.path.isdir(kubeconfig_dir):
        print(f"❌ ERREUR: Le répertoire '{kubeconfig_dir}' n'existe pas.", flush=True)
        return []
    
    kubeconfig_files = []
    
    # Utiliser os.scandir pour une meilleure performance
    with os.scandir(kubeconfig_dir) as entries:
        for entry in entries:
            if entry.is_file():
                kubeconfig_files.append(entry.path)
    
    if not kubeconfig_files:
        print(f"❌ ERREUR: Aucun fichier trouvé dans le répertoire '{kubeconfig_dir}'.", flush=True)
    else:
        print(f"📁 {len(kubeconfig_files)} fichiers trouvés dans le répertoire '{kubeconfig_dir}'.", flush=True)
        
    return kubeconfig_files

def merge_kubeconfig_files(kubeconfig_files, output_file):
    """
    Fusionne plusieurs fichiers kubeconfig en un seul fichier.
    Équivalent à: KUBECONFIG=file1:file2:... kubectl config view --flatten > output_file
    
    Args:
        kubeconfig_files (list): Liste des chemins vers les fichiers kubeconfig à fusionner
        output_file (str): Chemin du fichier de sortie fusionné
    
    Returns:
        bool: True si la fusion a réussi, False sinon
    """
    if not kubeconfig_files:
        print("❌ Aucun fichier kubeconfig à fusionner.", flush=True)
        return False
    
    # Vérifier que tous les fichiers existent
    for file_path in kubeconfig_files:
        if not os.path.isfile(file_path):
            print(f"❌ Le fichier {file_path} n'existe pas. Impossible de fusionner.", flush=True)
            return False
    
    try:
        # Créer la variable d'environnement KUBECONFIG avec les fichiers séparés par des ':'
        kubeconfig_env = ":".join(kubeconfig_files)
        
        # Exécuter la commande kubectl pour fusionner les fichiers
        env = os.environ.copy()
        env["KUBECONFIG"] = kubeconfig_env
        
        cmd = ["kubectl", "config", "view", "--flatten"]
        print(f"Exécution de la commande: KUBECONFIG={kubeconfig_env} {' '.join(cmd)}", flush=True)
        
        with open(output_file, 'w') as f:
            result = subprocess.run(cmd, stdout=f, env=env, check=True)
        
        if os.path.isfile(output_file) and os.path.getsize(output_file) > 0:
            print(f"✅ Fusion réussie. Fichier de sortie: {output_file}", flush=True)
            return True
        else:
            print(f"❌ Échec de la fusion. Le fichier de sortie {output_file} est vide ou n'existe pas.", flush=True)
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Erreur lors de l'exécution de kubectl: {e}", flush=True)
        return False
    except Exception as e:
        print(f"❌ Erreur inattendue lors de la fusion des fichiers: {e}", flush=True)
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Met à jour les noms de cluster, contexte et utilisateur dans les fichiers kubeconfig. "
                    "Le nom du cluster et du contexte devient le nom du fichier (sans 'config-' et sans extension). "
                    "L'utilisateur (par défaut 'kubernetes-admin') est renommé en 'admin-<nom_fichier_base>'."
    )
    parser.add_argument(
        "kubeconfig_files",
        metavar="KUBECONFIG_FILE",
        type=str,
        nargs='*',
        help="Chemins vers les fichiers kubeconfig à mettre à jour. Si non spécifié, tous les fichiers du répertoire 'kubeconfig' seront traités."
    )
    parser.add_argument(
        "--default-admin-user",
        type=str,
        default="kubernetes-admin",
        help="Le nom de l'utilisateur admin par défaut généré par kubeadm (défaut: kubernetes-admin)."
    )
    parser.add_argument(
        "--kubeconfig-dir",
        type=str,
        default="kubeconfig",
        help="Répertoire contenant les fichiers kubeconfig (défaut: 'kubeconfig')."
    )
    parser.add_argument(
        "--merge",
        action="store_true",
        help="Fusionner les fichiers kubeconfig traités en un seul fichier"
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default="/home/mini/.kube/config",
        help="Chemin du fichier de sortie pour la fusion (défaut: 'kubeconfig/config')"
    )

    args = parser.parse_args()

    # Si aucun fichier n'est spécifié, scanner le répertoire kubeconfig
    kubeconfig_files = args.kubeconfig_files
    if not kubeconfig_files:
        print(f"Aucun fichier spécifié, scan automatique du répertoire '{args.kubeconfig_dir}'...", flush=True)
        kubeconfig_files = scan_kubeconfig_directory(args.kubeconfig_dir)
        if not kubeconfig_files:
            print("❌ Aucun fichier à traiter. Fin du script.", flush=True)
            sys.exit(1)

    all_operations_successful = True
    print("=== Début du script de mise à jour des kubeconfigs ===", flush=True)
    for file_path_arg in kubeconfig_files:
        if not os.path.isfile(file_path_arg):
            print(f"❌ ERREUR: Le fichier spécifié '{file_path_arg}' n'existe pas ou n'est pas un fichier. Ignoré.", flush=True)
            all_operations_successful = False
            continue
        if not update_kubeconfig_all_names(file_path_arg, args.default_admin_user):
            all_operations_successful = False

    # Fusion des fichiers kubeconfig si demandé
    if args.merge and all_operations_successful:
        print("\n=== Fusion des fichiers kubeconfig ===", flush=True)
        # Créer le répertoire de sortie si nécessaire
        output_dir = os.path.dirname(args.output_file)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
                print(f"Répertoire créé: {output_dir}", flush=True)
            except Exception as e:
                print(f"❌ Erreur lors de la création du répertoire {output_dir}: {e}", flush=True)
                sys.exit(1)
                
        if merge_kubeconfig_files(kubeconfig_files, args.output_file):
            print(f"👍 Tous les fichiers ont été fusionnés avec succès dans {args.output_file}", flush=True)
        else:
            print(f"❌ La fusion des fichiers a échoué.", flush=True)
            sys.exit(1)

    print("\n=== Fin du script de mise à jour des kubeconfigs ===", flush=True)
    if not all_operations_successful:
        print("‼️ Attention: Au moins une opération de mise à jour de fichier a échoué ou un fichier n'a pas été trouvé. Veuillez vérifier les logs.", flush=True)
        sys.exit(1)
    else:
        print("👍 Toutes les opérations de mise à jour valides ont été effectuées.", flush=True)
