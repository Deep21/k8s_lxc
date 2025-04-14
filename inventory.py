#!/usr/bin/env python3

import subprocess
import json
import os

# Chemin vers la clé SSH privée
SSH_KEY_PATH = "/root/.ssh/k8s_lxd_key"

def get_lxc_containers():
    try:
        # Exécute la commande lxc list pour obtenir la liste des conteneurs
        result = subprocess.run(["lxc", "list", "--format", "json"], capture_output=True, text=True, check=True)
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
                    if name.startswith("master"):
                        inventory["masters"]["hosts"].append(name)
                    elif name.startswith("worker"):
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
        print(f"Erreur lors de l'exécution de la commande lxc: {e}", file=os.sys.stderr)
        return {"_meta": {"hostvars": {}}}
    except json.JSONDecodeError as e:
        print(f"Erreur lors du décodage JSON: {e}", file=os.sys.stderr)
        return {"_meta": {"hostvars": {}}}
    except Exception as e:
        print(f"Erreur inattendue: {e}", file=os.sys.stderr)
        return {"_meta": {"hostvars": {}}}

if __name__ == "__main__":
    inventory = get_lxc_containers()
    print(json.dumps(inventory, indent=2))
