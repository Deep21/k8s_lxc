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
    """Lit tous les fichiers manifest YAML et extrait les noms des clusters non provisionnés"""
    cluster_names = []
    try:
        files = [f for f in os.listdir(MANIFEST_DIR) if f.endswith(('.yaml', '.yml'))]
    except FileNotFoundError:
        print(f"Répertoire introuvable: {MANIFEST_DIR}", file=sys.stderr)
        return []

    for file in files:
        path = os.path.join(MANIFEST_DIR, file)
        try:
            with open(path, 'r') as f:
                manifest = yaml.safe_load(f)
                if manifest and 'metadata' in manifest and 'cluster_name' in manifest['metadata']:
                    provisioned = manifest.get('metadata', {}).get('provisioned', False) # False ou 'no' peut être utilisé
                    # Ajoute le cluster uniquement si 'provisioned' n'est pas True
                    if provisioned is not True:
                        cluster_names.append(manifest['metadata']['cluster_name'])
        except Exception as e:
            print(f"Erreur lors de la lecture du fichier {file}: {e}", file=sys.stderr)
            continue

    return cluster_names

def get_lxc_containers_data(cluster_name):
    """Récupère les données des conteneurs LXC (noms et hostvars) pour un cluster spécifique"""
    try:
        result = subprocess.run(
            ["lxc", "list", f"{cluster_name}-", "--format", "json"],
            capture_output=True, text=True, check=True
        )
        containers = json.loads(result.stdout)

        cluster_data = {
            "hostvars": {},
            "masters": [],
            "workers": []
        }

        for container in containers:
            name = container.get("name")
            status = container.get("status")

            if status == "Running":
                ip_address = None
                network_info = container.get("state", {}).get("network", {}).get("eth0", {})
                if network_info:
                    for address in network_info.get("addresses", []):
                        if address.get("family") == "inet":  # IPv4
                            ip_address = address.get("address")
                            break

                if ip_address and name:
                    host_vars = {
                        "ansible_host": ip_address,
                        "ansible_user": "ubuntu",
                        "ansible_ssh_private_key_file": SSH_KEY_PATH,
                        "ansible_ssh_common_args": "-o StrictHostKeyChecking=no",
                        "cluster_name": cluster_name
                    }
                    cluster_data["hostvars"][name] = host_vars

                    # Classification et ajout aux listes de noms
                    if f"{cluster_name}-master" in name:
                        cluster_data["masters"].append(name)
                    elif f"{cluster_name}-worker" in name:
                        cluster_data["workers"].append(name)

        return cluster_data

    except subprocess.CalledProcessError as e:
        print(f"Erreur lors de l'exécution de la commande lxc pour {cluster_name}: {e}", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"Erreur lors du décodage JSON pour {cluster_name}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Erreur inattendue pour {cluster_name}: {e}", file=sys.stderr)

    # Retourner une structure vide en cas d'erreur
    return {"hostvars": {}, "masters": [], "workers": []}

def get_hierarchical_inventory():
    """Construit l'inventaire hiérarchique pour tous les clusters non provisionnés"""
    cluster_names = list_cluster_names_from_manifests()

    if not cluster_names:
        print("Aucun cluster non provisionné trouvé.", file=sys.stderr)
        # Retourner un inventaire vide mais valide pour Ansible
        return {"_meta": {"hostvars": {}}, "all": {"children": ["ungrouped"]}}

    # Initialiser la structure d'inventaire finale
    inventory = {
        "_meta": {"hostvars": {}},
        "all": {"children": ["ungrouped"]}, # ungrouped est standard
        "masters": {"children": []},
        "workers": {"children": []}
        # Les groupes spécifiques aux clusters seront ajoutés ici
    }

    found_masters = False
    found_workers = False

    # Boucle sur chaque cluster identifié
    for cluster_name in cluster_names:
        # Obtenir les données des conteneurs pour ce cluster
        cluster_data = get_lxc_containers_data(cluster_name)

        # Fusionner les hostvars
        inventory["_meta"]["hostvars"].update(cluster_data.get("hostvars", {}))

        # Définir les noms des groupes spécifiques au cluster
        cluster_master_group = f"{cluster_name}_masters"
        cluster_worker_group = f"{cluster_name}_workers"

        has_masters = bool(cluster_data.get("masters"))
        has_workers = bool(cluster_data.get("workers"))

        # Si le cluster a des masters ou des workers, créer son groupe principal
        if has_masters or has_workers:
            inventory[cluster_name] = {"children": []}
            if cluster_name not in inventory["all"]["children"]:
                inventory["all"]["children"].append(cluster_name)

            # Gérer le groupe master spécifique au cluster
            if has_masters:
                inventory[cluster_master_group] = {"hosts": cluster_data["masters"]}
                inventory[cluster_name]["children"].append(cluster_master_group)
                if cluster_master_group not in inventory["masters"]["children"]:
                    inventory["masters"]["children"].append(cluster_master_group)
                found_masters = True

            # Gérer le groupe worker spécifique au cluster
            if has_workers:
                inventory[cluster_worker_group] = {"hosts": cluster_data["workers"]}
                inventory[cluster_name]["children"].append(cluster_worker_group)
                if cluster_worker_group not in inventory["workers"]["children"]:
                    inventory["workers"]["children"].append(cluster_worker_group)
                found_workers = True

    # Ajouter les groupes globaux 'masters' et 'workers' à 'all.children' s'ils contiennent des sous-groupes
    if found_masters and "masters" not in inventory["all"]["children"]:
        inventory["all"]["children"].append("masters")
    if found_workers and "workers" not in inventory["all"]["children"]:
        inventory["all"]["children"].append("workers")

    # Optionnel: Trier les enfants pour la cohérence
    inventory["all"]["children"].sort()
    inventory["masters"]["children"].sort()
    inventory["workers"]["children"].sort()
    for cluster_name in cluster_names:
        if cluster_name in inventory:
            inventory[cluster_name]["children"].sort()


    return inventory

def parse_args():
    """Parse les arguments de ligne de commande pour Ansible"""
    if len(sys.argv) > 1:
        if sys.argv[1] == '--list':
            return get_hierarchical_inventory()
        elif sys.argv[1] == '--host' and len(sys.argv) > 2:
            # Pour Ansible 2.x+, _meta contient tout, retourner vide pour --host
            # hostname = sys.argv[2]
            # inventory = get_hierarchical_inventory() # Recalculate inventory
            # return inventory.get("_meta", {}).get("hostvars", {}).get(hostname, {}) # Return specific host vars if needed by older Ansible
            return {} # Standard pour Ansible >= 2.0
    # Si aucun argument valide pour Ansible n'est fourni, retourner vide
    return {}

if __name__ == "__main__":
    inventory_data = parse_args()
    print(json.dumps(inventory_data, indent=2))