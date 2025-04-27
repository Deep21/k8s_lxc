#!/usr/bin/env python3

import json
import sys

def generate_inventory():
    # Votre logique pour générer l'inventaire
    inventory = {
        "all": {
            "children": {
                "group1": {
                    "hosts": ["host1", "host2"]
                }
            }
        }
    }
    return inventory

def empty_inventory():
    return {"_meta": {"hostvars": {}}}

def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == '--list':
            print(json.dumps(generate_inventory()))
        elif sys.argv[1] == '--host' and len(sys.argv) > 2:
            # Pour --host, on retourne un objet vide ou les variables d'hôte
            print(json.dumps({}))
        else:
            # Argument non reconnu
            print(json.dumps(empty_inventory()))
    else:
        # Pas d'argument, on affiche l'inventaire complet
        print(json.dumps(generate_inventory()))

if __name__ == "__main__":
    main()
