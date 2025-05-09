from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from dotenv import load_dotenv
import sqlite3
import logging
import os

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Chargement des variables d'environnement
load_dotenv()

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "http://localhost:3000"}})
#DATABASE = os.getenv('DATABASE_URL', './Bdd_Systeme_ACRN_NEW.db').replace('sqlite:///', '')
DATABASE = os.getenv('DATABASE_URL', 'ACRN_API_REST_EMBARQ/Bdd_Systeme_ACRN_NEW.db').replace('sqlite:///', '')
DictDesriptionTable = {}  

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn



#======================================================================================================
# ROUTES STANDARDS POUR LE LOGICIEL EMBARQUE
#======================================================================================================


def get_tables():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tables

def get_table_columns(table_name):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns_info = []
    for row in cursor.fetchall():
        technical_name = row[1]
        columns_info.append({
            'name': technical_name,
            'type': row[2],
            'not_null': bool(row[3]),
            'default_value': row[4],
            'primary_key': bool(row[5])
        })
    conn.close()
    return columns_info


def get_primary_key(table_name):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    primary_key = None
    for row in cursor.fetchall():
        if row[5] == 1:  # pk column
            primary_key = row[1]
            break
    conn.close()
    return primary_key

# Middleware pour le logging des requêtes
@app.before_request
def log_request_info():
    logger.info(f"Requête {request.method} sur {request.path}")
    if request.is_json:
        logger.info(f"Données JSON: {request.get_json()}")
    elif request.form:
        logger.info(f"Données form: {request.form}")

# Route racine pour lister toutes les tables disponibles
@app.route('/', methods=['GET'])
def list_tables():
    return jsonify({
        'tables': get_tables(),
        'message': 'Utilisez /<nom_table> pour accéder aux données'
    })

# Route pour obtenir la structure d'une table
@app.route('/<table_name>/structure', methods=['GET'])
def get_table_structure(table_name):
    if table_name not in get_tables():
        return jsonify({'error': 'Table non trouvée'}), 404
    columns = get_table_columns(table_name)
    return jsonify({
        'columns': columns
    })

# Route GET pour tous les enregistrements d'une table
@app.route('/<table_name>', methods=['GET'])
def get_all_records(table_name):
    if table_name not in get_tables():
        return jsonify({'error': 'Table non trouvée'}), 404
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name}")
    records = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(records)

# Route GET pour un enregistrement spécifique
@app.route('/<table_name>/<id>', methods=['GET'])
def get_record(table_name, id):
    if table_name not in get_tables():
        return jsonify({'error': 'Table non trouvée'}), 404

    primary_key = get_primary_key(table_name)
    if not primary_key:
        return jsonify({'error': 'Clé primaire non trouvée'}), 400

    conn = get_db()
    cursor = conn.cursor()

    # Si la table est TableProfils, on joint avec le profil d'origine
    if table_name == "TableProfils":
        cursor.execute("""
            SELECT p.*, po.NomProfil AS NomProfilOrigine
            FROM TableProfils p
            LEFT JOIN TableProfils po ON p.IdProfilOrigineCopie = po.IdProfil
            WHERE p.IdProfil = ?
        """, (id,))
    else:
        cursor.execute(f"SELECT * FROM {table_name} WHERE {primary_key} = ?", (id,))

    record = cursor.fetchone()
    conn.close()

    if record is None:
        return jsonify({'error': 'Enregistrement non trouvé'}), 404

    return jsonify(dict(record))


# Route POST pour créer un enregistrement
@app.route('/<table_name>', methods=['POST'])
def create_record(table_name):
    if table_name not in get_tables():
        return jsonify({'error': 'Table non trouvée'}), 404
    
    data = request.get_json()
    columns = get_table_columns(table_name)
    
    # Vérification des colonnes requises
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    required_columns = [row[1] for row in cursor.fetchall() if row[3] == 1 and row[1] != get_primary_key(table_name)]
    missing_columns = [col for col in required_columns if col not in data]
    
    if missing_columns:
        conn.close()
        return jsonify({
            'error': f'Colonnes manquantes: {", ".join(missing_columns)}'
        }), 400
    
    # Construction de la requête SQL
    placeholders = ', '.join(['?' for _ in data])
    columns_str = ', '.join(data.keys())
    values = tuple(data.values())
    
    cursor.execute(f"INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})", values)
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    
    return jsonify({'id': new_id, **data}), 201

# Route PUT pour mettre à jour un enregistrement
@app.route('/<table_name>/<id>', methods=['PUT'])
def update_record(table_name, id):
    if table_name not in get_tables():
        return jsonify({'error': 'Table non trouvée'}), 404
    
    primary_key = get_primary_key(table_name)
    if not primary_key:
        return jsonify({'error': 'Clé primaire non trouvée'}), 400
    
    data = request.get_json()
    
    # Vérification que l'enregistrement existe
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(f"SELECT {primary_key} FROM {table_name} WHERE {primary_key} = ?", (id,))
    if cursor.fetchone() is None:
        conn.close()
        return jsonify({'error': 'Enregistrement non trouvé'}), 404
    
    # Construction de la requête SQL
    set_clause = ', '.join([f"{k} = ?" for k in data.keys()])
    values = tuple(data.values()) + (id,)
    
    cursor.execute(f"UPDATE {table_name} SET {set_clause} WHERE {primary_key} = ?", values)
    conn.commit()
    conn.close()
    
    return jsonify({'id': id, **data})

# Route DELETE pour supprimer un enregistrement
@app.route('/<table_name>/<id>', methods=['DELETE'])
def delete_record(table_name, id):
    if table_name not in get_tables():
        return jsonify({'error': 'Table non trouvée'}), 404
    
    primary_key = get_primary_key(table_name)
    if not primary_key:
        return jsonify({'error': 'Clé primaire non trouvée'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Vérification que l'enregistrement existe
    cursor.execute(f"SELECT {primary_key} FROM {table_name} WHERE {primary_key} = ?", (id,))
    if cursor.fetchone() is None:
        conn.close()
        return jsonify({'error': 'Enregistrement non trouvé'}), 404
    
    cursor.execute(f"DELETE FROM {table_name} WHERE {primary_key} = ?", (id,))
    conn.commit()
    conn.close()
    
    return '', 204





#======================================================================================================
# ROUTES SPECIFIQUES POUR LE LOGICIEL EMBARQUE
#======================================================================================================

#======================================================================================================
# FONCTION GENERALES

def get_table_description_dict():
    """
    Crée un dictionnaire à partir de la table TableDescriptionTable
    avec le champ NomComplet comme clé.
    
    Returns:
        dict: Dictionnaire avec NomComplet comme clé et les autres champs comme valeurs
    """
    try:

        
        # Connexion à la base de données
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Récupération des données
        cursor.execute("SELECT * FROM TableDescriptionTable")
        rows = cursor.fetchall()
        
        # Création du dictionnaire
        description_dict = {}
        for row in rows:
            row_dict = dict(row)
            nom_complet = row_dict.get('NomComplet')
            if nom_complet:
                description_dict[nom_complet] = row_dict
        
        return description_dict
        
    except Exception as e:
        print(f"Erreur lors de la création du dictionnaire : {str(e)}")
        return {}
    finally:
        if 'conn' in locals():
            conn.close()

def ConvertiRequeteEnJSON(query, params=None):
    """
    Analyse une requête SQL et retourne les métadonnées et les données.
    
    Args:
        query (str): La requête SQL à analyser
        params (tuple, optional): Les paramètres de la requête
        
    Returns:
        dict: Un dictionnaire contenant :
            - metadata: Liste des champs avec leurs descriptions
            - data: Les données de la requête
    """
    try:
        # Connexion à la base de données
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row  # Pour avoir accès aux colonnes par nom
        cursor = conn.cursor()
        
        # Exécution de la requête
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
            
        # Récupération des données
        data = cursor.fetchall()
        
        # Récupération des métadonnées des colonnes
        columns = cursor.description
        
        # Construction du résultat
        result = {
            "metadata": [],
            "data": []
        }
        
        # Extraction des noms de tables de la requête
        tables = []
        if "FROM" in query:
            from_part = query.split("FROM")[1].split("WHERE")[0].strip()
            tables = [t.strip() for t in from_part.split("JOIN")[0].split(",")]
            if "JOIN" in from_part:
                join_tables = from_part.split("JOIN")[1:]
                for join in join_tables:
                    tables.append(join.split("ON")[0].strip())
        
        # Traitement des métadonnées
        for col in columns:
            # Détermination de la table d'origine
            table_name = "N/A"
            for table in tables:
                if col[0].startswith(table + "."):
                    table_name = table
                    break
            
            # Construction du NomComplet pour la recherche dans le dictionnaire
            nom_complet = col[0]  # Le nom complet est déjà dans le format attendu grâce à l'alias dans la requête
            
            # Récupération des informations du dictionnaire
            dict_info = DictDesriptionTable.get(nom_complet, {})
            
            field_info = {
                "NomComplet": nom_complet,
                "libelle": dict_info.get('LibelleChamp', "Libelle Introuvable"),
                "EstScrutable": dict_info.get('EstScrutable', False),  # Par défaut True si non spécifié
                "EstFiltrable": dict_info.get('EstFiltrable', True),  # Par défaut True si non spécifié
                "EstModifiable": dict_info.get('EstModifiable', True),  # Par défaut True si non spécifié
                "TypeChamp": dict_info.get('TypeChamp', False),  # Par défaut True si non spécifié
                "ValeurParDefaut": dict_info.get('ValeurParDefaut', True),  # Par défaut True si non spécifié
            }   
            result["metadata"].append(field_info)
        
        # Traitement des données
        for row in data:
            row_dict = dict(row)  # Conversion de sqlite3.Row en dict
            result["data"].append(row_dict)
            
        return result
        
    except Exception as e:
        return {"error": str(e)}
    finally:
        if 'conn' in locals():
            conn.close()

def GenereSQLPourSelectEtoile(NomTable):
     # Connexion à la base de données
        conn = get_db()
        cursor = conn.cursor()
        
        # Récupération de la structure de la table
        cursor.execute(f'PRAGMA table_info({NomTable})')
        columns = cursor.fetchall()
        
        # Construction de la requête SQL avec tous les champs
        select_parts = []
        for col in columns:
            column_name = col[1]  # Le nom de la colonne est dans la deuxième position
            select_parts.append(f'{NomTable}.{column_name} as "{NomTable}..{column_name}.."')
        
        query = f"""
        SELECT 
            {',\n            '.join(select_parts)}
        FROM {NomTable}
        """

        return(query)
#======================================================================================================





#======================================================================================================
# PROFILS

# Route spécifique pour l'ajout de profil basé sur un profil existant
@app.route("/profil/duplicate", methods=["POST", "OPTIONS"])
def duplicate_profil():
    if request.method == "OPTIONS":
        response = make_response()
        response.headers["Access-Control-Allow-Origin"] = "http://localhost:3000"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        return response, 204

    data = request.get_json()
    
    # Vérification des données requises
    if not data or 'idProfilOrigineCopie' not in data or 'nom' not in data:
        return jsonify({'error': 'Les champs id et nom sont requis'}), 400
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Récupération du profil d'origine
        cursor.execute("SELECT * FROM TableProfils WHERE idProfil = ?", (data['idProfilOrigineCopie'],))
        original_profil = cursor.fetchone()
        
        if original_profil is None:
            conn.close()
            return jsonify({'error': 'Profil d\'origine non trouvé'}), 404
        
        # Création du nouveau profil avec le nouveau nom
        profil_dict = dict(original_profil)
        profil_dict['NomProfil'] = data['nom']

        # Suppression de l'id pour la création du nouveau profil
        del profil_dict['IdProfil']
        profil_dict['IdProfilOrigineCopie'] = data['idProfilOrigineCopie']
        del profil_dict['NomProfilDefaut']
        
        # Construction de la requête SQL
        columns = ', '.join(profil_dict.keys())
        placeholders = ', '.join(['?' for _ in profil_dict])
        values = tuple(profil_dict.values())
        
        cursor.execute(f"INSERT INTO TableProfils ({columns}) VALUES ({placeholders})", values)



        #==============================================
        # Copie des droits
        #==============================================     

        new_id = cursor.lastrowid
        
        # Récupération des droits du profil d'origine
        cursor.execute("SELECT * FROM TableProfilsDroits WHERE IdProfil = ?", (data['idProfilOrigineCopie'],))
        droits_origine = cursor.fetchall()
        
        # Pour chaque droit, création d'un nouvel enregistrement avec le nouvel IdProfil
        for droit in droits_origine:
            droit_dict = dict(droit)
            # Suppression de l'id pour la création du nouveau droit
            del droit_dict['IdProfilDroit']
            # Mise à jour de l'IdProfil avec le nouvel ID
            droit_dict['IdProfil'] = new_id
            
            # Construction de la requête SQL pour l'insertion du droit
            columns = ', '.join(droit_dict.keys())
            placeholders = ', '.join(['?' for _ in droit_dict])
            values = tuple(droit_dict.values())
            
            cursor.execute(f"INSERT INTO TableProfilsDroits ({columns}) VALUES ({placeholders})", values)
        
        # Commit de toutes les modifications
        conn.commit()
        
        return jsonify({'idProfil': new_id, **profil_dict}), 201
        
    except Exception as e:
        # En cas d'erreur, on fait un rollback
        if 'conn' in locals():
            conn.rollback()
        return jsonify({'error': f'Erreur lors de la duplication du profil: {str(e)}'}), 500
        
    finally:
        # On s'assure que la connexion est toujours fermée
        if 'conn' in locals():
            conn.close()

# Route pour ajouter ou supprimer des droits d'un profil
@app.route('/profil/droits', methods=['PUT'])
def modifier_droits_profil():
    data = request.get_json()
    
    # Vérification des données requises
    if not data or 'idProfil' not in data or 'idDroit' not in data or 'typeAction' not in data:
        return jsonify({'error': 'Les champs idProfil, idDroit et typeAction sont requis'}), 400
    
    # Vérification du type d'action
    if data['typeAction'] not in ['Ajouter', 'Supprimer']:
        return jsonify({'error': 'Le typeAction doit être "Ajouter" ou "Supprimer"'}), 400
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Vérification que le profil existe
        cursor.execute("SELECT idProfil FROM TableProfils WHERE idProfil = ?", (data['idProfil'],))
        if cursor.fetchone() is None:
            conn.close()
            return jsonify({'error': 'Profil non trouvé'}), 404
        
        # Vérification que le droit existe
        cursor.execute("SELECT idDroit FROM TableDroits WHERE idDroit = ?", (data['idDroit'],))
        if cursor.fetchone() is None:
            conn.close()
            return jsonify({'error': 'Droit non trouvé'}), 404
        
        if data['typeAction'] == 'Ajouter':
            # Vérification si le droit existe déjà pour ce profil
            cursor.execute("""
                SELECT IdProfilDroit 
                FROM TableProfilsDroits 
                WHERE IdProfil = ? AND IdDroit = ?
            """, (data['idProfil'], data['idDroit']))
            
            if cursor.fetchone() is not None:
                conn.close()
                return jsonify({'error': 'Ce droit est déjà associé au profil'}), 400
            
            # Ajout du droit
            cursor.execute("""
                INSERT INTO TableProfilsDroits (IdProfil, IdDroit)
                VALUES (?, ?)
            """, (data['idProfil'], data['idDroit']))
            
        else:  # Supprimer
            # Suppression du droit
            cursor.execute("""
                DELETE FROM TableProfilsDroits 
                WHERE IdProfil = ? AND IdDroit = ?
            """, (data['idProfil'], data['idDroit']))
        
        conn.commit()
        
        # Récupération des droits actuels du profil pour la réponse
        cursor.execute("""
            SELECT d.* 
            FROM TableDroits d
            INNER JOIN TableProfilsDroits pd ON d.IdDroit = pd.IdDroit
            WHERE pd.IdProfil = ?
        """, (data['idProfil'],))
        
        droits = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'message': f'Droit {"ajouté" if data["typeAction"] == "Ajouter" else "supprimé"} avec succès',
            'idProfil': data['idProfil'],
            'droits': droits
        }), 200
        
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
        return jsonify({'error': f'Erreur lors de la modification des droits: {str(e)}'}), 500
        
    finally:
        if 'conn' in locals():
            conn.close()

# Route spécifique pour la suppression d'un profil
@app.route('/profil/suppression', methods=['PUT'])
def supprimer_profil():
    data = request.get_json()
    
    # Vérification des données requises
    if not data or 'idProfil' not in data:
        return jsonify({'error': 'Le champ idProfil est requis'}), 400
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Vérification que le profil existe
        cursor.execute("SELECT * FROM TableProfils WHERE IdProfil = ?", (data['idProfil'],))
        profil = cursor.fetchone()
        if profil is None:
            conn.close()
            return jsonify({'error': 'Profil non trouvé'}), 404
        
        # 1. Mise à jour des utilisateurs associés (EstCloture = 1)
        cursor.execute("""
            UPDATE TableUtilisateurs 
            SET EstCloture = 1
            WHERE IdProfil = ?
        """, (data['idProfil'],))
        
        # 2. Suppression des droits associés
        #cursor.execute("""
        #    DELETE FROM TableProfilsDroits 
        #    WHERE IdProfil = ?
        #""", (data['idProfil'],))
        
        # 3. Mise à jour du profil (EstCloture = 1)
        cursor.execute("""
            UPDATE TableProfils 
            SET EstCloture = 1
            WHERE IdProfil = ?
        """, (data['idProfil'],))
        
        conn.commit()
        
        return jsonify({
            'message': 'Profil supprimé avec succès',
            'idProfil': data['idProfil']
        }), 200
        
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
        return jsonify({'error': f'Erreur lors de la suppression du profil: {str(e)}'}), 500
        
    finally:
        if 'conn' in locals():
            conn.close()

#======================================================================================================






#======================================================================================================
# UTILISATEURS

# Route spécifique pour la suppression d'un profil
@app.route('/Capteur/TableauUtilisateurs', methods=['GET'])
def lire_tableau_utilisateurs():
    
    query = """
    SELECT 
        u.Nom as "TableUtilisateurs..Nom..",
        u.MDP as "TableUtilisateurs..MDP..",
        p.NomProfil as "TableProfils..NomProfil..",
        u.IdProfil as "TableUtilisateurs..IdProfil.."
    FROM TableUtilisateurs u
    INNER JOIN TableProfils p ON u.IdProfil = p.IdProfil
    """
    
    result = ConvertiRequeteEnJSON(query)
    return result
#======================================================================================================








#======================================================================================================
# Overloads

# Route spécifique pour la lecture du tableau de capteurs
@app.route('/Capteur/TableauOverloads', methods=['GET'])
def lire_tableau_overloads():
    try:
        conn = get_db()
        query=GenereSQLPourSelectEtoile('TableOverloads')
        print(query)
        return ConvertiRequeteEnJSON(query)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

#======================================================================================================



#======================================================================================================
# Droits

# Route spécifique pour la lecture du tableau de capteurs
@app.route('/Capteur/TableauDroits', methods=['GET'])
def lire_tableau_Droits():
    try:
        conn = get_db()
        query="""
            SELECT
            TableDroits.IdDroit as 'TableDroits..IdDroit..',
            TableDroits.Nom as 'TableDroits..Nom..',
            TableDroits2.nom as 'TableDroits..IdDroitPrerequis..',
            TableDroits.EstModifiable as 'TableDroits..EstModifiable..',
            TableDroits.EstAffichable as 'TableDroits..EstAffichable..',
            TableDroits.ReferenceTraduction as 'TableDroits..ReferenceTraduction..'
            FROM TableDroits left join TableDroits TableDroits2 on TableDroits.IdDroitPrerequis=TableDroits2.IdDroit
            """
        print(query)
        return ConvertiRequeteEnJSON(query)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()

#======================================================================================================





#======================================================================================================
# CAPTEURS

# Route spécifique pour la lecture du tableau de capteurs
@app.route('/Capteur/TableauCapteurs', methods=['GET'])
def lire_tableau_capteurs():
    try:
        conn = get_db()
        query=GenereSQLPourSelectEtoile('TableCapteur')
        return ConvertiRequeteEnJSON(query)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()


#======================================================================================================








if __name__ == '__main__':
    DictDesriptionTable = get_table_description_dict()

    app.run(debug=True) 

    