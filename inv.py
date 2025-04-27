#!/usr/bin/env python3

import subprocess
import json
import os
import yaml
import sys

# Chemin vers la clé SSH privée
SSH_KEY_PATH = "/root/.ssh/k8s_lxd_key"
# Chemin vers le fichier manifest
MANIFEST_PATH = "./data/manifest-test2.yaml"

def read_manifest():
    """Lit le fichier manifest YAML et extrait le nom du cluster"""
    try:
        with open(MANIFEST_PATH, 'r') as f:
            manifest = yaml.safe_load(f)
            
        # Vérifier la structure du manifest
        if not manifest or 'metadata' not in manifest:
            print(f"Structure du manifest invalide dans {MANIFEST_PATH}", file=sys.stderr)
            return None
            
        cluster_name = manifest['metadata']['cluster_name']
        return cluster_name
        
    except FileNotFoundError:
        print(f"Fichier manifest introuvable: {MANIFEST_PATH}", file=sys.stderr)
        return None
    except yaml.YAMLError as e:
        print(f"Erreur lors du parsing YAML: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Erreur inattendue lors de la lecture du manifest: {e}", file=sys.stderr)
        return None

def get_lxc_containers():
    try:
        # Lire le manifest pour obtenir le nom du cluster
        cluster_name = read_manifest()
        
        if not cluster_name:
            print("Impossible de continuer sans nom de cluster valide", file=sys.stderr)
            return {"_meta": {"hostvars": {}}}
        
        # Exécute la commande lxc list avec un filtre sur le nom du cluster
        result = subprocess.run(["lxc", "list", f"{cluster_name}-", "--format", "json"], 
                               capture_output=True, text=True, check=True)
        containers = json.loads(result.stdout)
        
        # Prépare la structure de l'inventaire Ansible
        inventory = {
            "_meta": {
                "hostvars": {}
            }
        }
        
        # Groupes principaux
        inventory["all"] = {"children": ["masters", "workers"]}
        inventory["masters"] = {"hosts": []}
        inventory["workers"] = {"hosts": []}
        
        
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
        print(f"Erreur lors de l'exécution de la commande lxc: {e}", file=sys.stderr)
        return {"_meta": {"hostvars": {}}}
    except json.JSONDecodeError as e:
        print(f"Erreur lors du décodage JSON: {e}", file=sys.stderr)
        return {"_meta": {"hostvars": {}}}
    except Exception as e:
        print(f"Erreur inattendue: {e}", file=sys.stderr)
        return {"_meta": {"hostvars": {}}}

def parse_args():
    """Parse les arguments de ligne de commande"""
    # Ansible appelle le script avec --list ou --host 
    if len(sys.argv) > 1:
        if sys.argv == '--list':
            return get_lxc_containers()
        elif sys.argv == '--host' and len(sys.argv) > 2:
            # Retourne les variables d'hôte pour un hôte spécifique
            # Pour simplifier, nous retournons un dictionnaire vide
            # car toutes les variables d'hôte sont déjà dans _meta
            return {}
    
    # Si aucun argument valide n'est fourni, retourne l'inventaire complet
    return get_lxc_containers()

if __name__ == "__main__":
    inventory = parse_args()
    print(json.dumps(inventory, indent=2))
