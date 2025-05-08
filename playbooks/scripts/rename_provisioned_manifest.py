#!/usr/bin/env python3
import os
import sys
import argparse
import logging
from pathlib import Path

# Configuration simple du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def rename_manifest(cluster_name, playbook_dir_str):
    """
    Renomme le fichier manifest-<cluster_name>.yaml en manifest-<cluster_name>.provisioned
    si les conditions sont remplies.
    """
    try:
        playbook_dir = Path(playbook_dir_str)
        data_dir = playbook_dir / "../data" 
        
        source_filename = f"manifest-{cluster_name}.yaml"
        dest_filename = f"manifest-{cluster_name}.provisioned"
        
        source_path = data_dir / source_filename
        dest_path = data_dir / dest_filename

        logger.info(f"Vérification pour le cluster: {cluster_name}")
        logger.info(f"Chemin source: {source_path}")
        logger.info(f"Chemin destination: {dest_path}")

        if not source_path.exists():
            logger.warning(f"Le fichier source n'existe pas, renommage ignoré: {source_path}")
            return False, "Source file not found, skipped" 

        if dest_path.exists():
            logger.info(f"Le fichier destination existe déjà, renommage ignoré (idempotent): {dest_path}")
            return False, "Destination file already exists, skipped"

        logger.info(f"Renommage de '{source_path}' vers '{dest_path}'...")
        source_path.rename(dest_path)
        logger.info("Renommage réussi.")
        return True, "Renamed successfully"

    except OSError as e:
        logger.error(f"Erreur OS lors du renommage pour {cluster_name}: {e}")
        return False, f"OS Error: {e}"
    except Exception as e:
        logger.error(f"Erreur inattendue pour {cluster_name}: {e}")
        return False, f"Unexpected Error: {e}"

def main():
    parser = argparse.ArgumentParser(description="Renomme un fichier manifest après provisionnement.")
    parser.add_argument("cluster_name", help="Nom du cluster dont le manifest doit être renommé.")
    parser.add_argument("playbook_dir", help="Chemin absolu vers le répertoire du playbook Ansible.")
    
    args = parser.parse_args()

    message = rename_manifest(args.cluster_name, args.playbook_dir)

    print(message)

    sys.exit(0 if "Error" not in message else 1)

if __name__ == "__main__":
    main()
