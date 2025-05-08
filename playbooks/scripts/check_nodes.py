#!/usr/bin/env python3
import time
import subprocess
import sys
import json

def check_nodes_ready(kubeconfig_path, retries=30, delay=10):
    """
    Vérifie si tous les nœuds Kubernetes sont en état Ready.
    
    Args:
        kubeconfig_path (str): Chemin vers le fichier kubeconfig
        retries (int): Nombre de tentatives
        delay (int): Délai entre les tentatives en secondes
    
    Returns:
        dict: Résultat avec statut et message
    """
    result = {
        "success": False,
        "message": "",
        "attempts": 0
    }
    
    for attempt in range(retries):
        result["attempts"] = attempt + 1
        try:
            # Exécuter la commande kubectl get nodes
            cmd_result = subprocess.run(
                ["kubectl", "get", "nodes", "--kubeconfig", kubeconfig_path],
                capture_output=True,
                text=True,
                check=True
            )
            output = cmd_result.stdout
            
            # Vérifier si 'NotReady' est dans la sortie
            if 'NotReady' not in output:
                result["success"] = True
                result["message"] = f"Tous les nœuds sont prêts après {attempt + 1} tentative(s)."
                break
            else:
                # Attendre avant la prochaine tentative
                time.sleep(delay)
        except subprocess.CalledProcessError as e:
            result["message"] = f"Erreur lors de l'exécution de kubectl: {e.stderr}"
            break
        except Exception as e:
            result["message"] = f"Erreur inattendue: {str(e)}"
            break
    
    if not result["success"] and not result["message"]:
        result["message"] = f"Certains nœuds ne sont pas prêts après {retries} tentatives."
    
    return result

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python check_nodes.py <kubeconfig_path>")
        sys.exit(1)
    
    kubeconfig_path = sys.argv[1]
    result = check_nodes_ready(kubeconfig_path)
    
    # Sortie JSON pour Ansible
    print(json.dumps(result))
    sys.exit(0 if result["success"] else 1)
