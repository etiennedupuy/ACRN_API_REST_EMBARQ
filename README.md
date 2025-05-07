# API RESTful ACRN

## Installation de l'environnement local

1. Créer un environnement virtuel Python :
```bash
python -m venv venv
```

2. Activer l'environnement virtuel :
- Windows :
```bash
.\venv\Scripts\activate
```
- Linux/Mac :
```bash
source venv/bin/activate
```

3. Installer les dépendances :
```bash
pip install -r requirements.txt
```

4. Configuration de l'environnement :
- Créer un fichier `.env` à la racine du projet avec le contenu suivant :
```
FLASK_APP=app.py
FLASK_ENV=development
DATABASE_URL=sqlite:///Bdd_Systeme_ACRN.db
SECRET_KEY=votre_cle_secrete_ici
```

5. Lancer l'application :
```bash
flask run
```

## Structure du projet
- `Bdd_Systeme_ACRN.db` : Base de données SQLite
- `requirements.txt` : Dépendances Python
- `.env` : Variables d'environnement (à créer) 