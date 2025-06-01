# k8s_lxc - Déploiement automatisé de clusters Kubernetes sur LXC

Ce projet permet de déployer rapidement un ou plusieurs clusters Kubernetes sur des conteneurs LXC, offrant une solution légère pour le développement, les tests et l'apprentissage de Kubernetes.

## Prérequis

- Ansible 2.10+ avec la collection `community.general`
- LXD/LXC installé et configuré sur la machine hôte
- Accès sudo pour l'utilisateur exécutant Ansible
- Python 3.6+ avec les modules `yaml` et `jinja2`

## Architecture

Le projet déploie une infrastructure Kubernetes complète sur des conteneurs LXC :
- Nœuds master Kubernetes (controlplane)
- Nœuds worker Kubernetes
- Configuration réseau avec Flannel ou Calico (configurable)
- Génération automatique des fichiers kubeconfig

### Structure du projet
k8s_lxc/
├── ansible.cfg # Configuration Ansible
├── group_vars/ # Variables globales
│ └── all.yaml # Variables communes à tous les playbooks
├── inventory/ # Inventaire dynamique
│ └── inventory.py # Script d'inventaire pour détecter les conteneurs
├── playbooks/ # Playbooks Ansible
│ ├── first.yaml # Playbook principal de déploiement
│ ├── down.yaml # Suppression des clusters
│ └── scripts/ # Scripts auxiliaires
├── roles/ # Rôles Ansible
│ ├── kubernetes-common/ # Configuration commune à tous les nœuds
│ ├── kubernetes-master/ # Configuration des nœuds master
│ ├── kubernetes-worker/ # Configuration des nœuds worker
│ └── lxc-setup/ # Création et configuration des conteneurs LXC
└── tests/ # Tests automatisés
└── test_deployment.py # Tests avec pytest et testinfra


## Utilisation

sudo ansible-playbook playbooks/up.yaml --extra-vars '{"cluster_names": ["dakund"]'}

### Déploiement d'un cluster
sudo ansible-playbook -i inventory/inventory.py playbooks/first.yaml --extra-vars '{"cluster_names": ["production"], "k8s_worker_node_count": 3}'

### Déploiement de plusieurs clusters
sudo ansible-playbook -i inventory/inventory.py playbooks/first.yaml --extra-vars '{"cluster_names": ["dev", "staging", "prod"], "k8s_worker_node_count": 2}'

### Suppression des clusters
sudo ansible-playbook -i inventory/inventory.py playbooks/down.yaml --extra-vars '{"cluster_names": ["dev"]}'


## Configuration

Vous pouvez personnaliser le déploiement en modifiant les variables dans `group_vars/all.yaml` ou en les passant via `--extra-vars`.

### Variables principales

| Variable | Description | Valeur par défaut |
|----------|-------------|-------------------|
| `cluster_names` | Liste des noms de clusters à déployer | `["default"]` |
| `k8s_master_node_count` | Nombre de nœuds master par cluster | `1` |
| `k8s_worker_node_count` | Nombre de nœuds worker par cluster | `2` |
| `k8s_version` | Version de Kubernetes à installer | `1.26.1` |
| `lxd_image_alias` | Image LXD à utiliser | `ubuntu/jammy` |

## Dépannage

### Problèmes courants

1. **Les conteneurs ne démarrent pas**
   - Vérifiez que LXD est correctement configuré : `lxc list`
   - Assurez-vous que les profils nécessaires sont créés : `lxc profile list`

2. **Les nœuds worker ne rejoignent pas le cluster**
   - Vérifiez la connectivité réseau entre les conteneurs
   - Consultez les logs kubelet : `journalctl -u kubelet`

## Contribution

Les contributions sont les bienvenues ! Veuillez suivre ces étapes :
1. Forkez le dépôt
2. Créez une branche pour votre fonctionnalité
3. Soumettez une pull request

## Licence

Ce projet est sous licence MIT.
