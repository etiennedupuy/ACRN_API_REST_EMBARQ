from flask import Flask, request, jsonify
import sqlite3
import logging
import os
from dotenv import load_dotenv

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Chargement des variables d'environnement
load_dotenv()

app = Flask(__name__)
DATABASE = os.getenv('DATABASE_URL', 'Bdd_Systeme_ACRN_NEW.db').replace('sqlite:///', '')

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

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
    columns = [row[1] for row in cursor.fetchall()]
    conn.close()
    return columns

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
    return jsonify({
        'columns': get_table_columns(table_name),
        'primary_key': get_primary_key(table_name)
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

if __name__ == '__main__':
    app.run(debug=True) 
    print("coucou")