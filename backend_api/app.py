import os
import re
import io
import camelot
import pandas as pd
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# --- Configuração do Servidor Flask ---
app = Flask(__name__)
CORS(app)

# ==============================================================================
# FUNÇÃO DE EXTRAÇÃO (SEM ALTERAÇÃO)
# ==============================================================================

def extrair_tabelas_camelot_stream(file_object, paginas_str):
    print(f"\nIniciando extração com Camelot (modo STREAM) nas páginas: {paginas_str}...")
    try:
        tabelas = camelot.read_pdf(file_object, pages=paginas_str, flavor='stream', row_tol=10)
    except Exception as e:
        print(f"Ocorreu um erro ao ler o PDF com Camelot: {e}")
        return None
    if not tabelas or len(tabelas) == 0:
        print("Nenhuma tabela foi detectada pelo Camelot nas páginas especificadas.")
        return None
    print(f"SUCESSO NA EXTRAÇÃO! Foram detectadas {len(tabelas)} tabelas.")
    return pd.concat([tabela.df for tabela in tabelas], ignore_index=True)

# ==============================================================================
# ROTA DA API (MODIFICADA PARA MODO DIAGNÓSTICO)
# ==============================================================================

@app.route('/process', methods=['POST'])
def process_file_direct():
    if 'pdf_file' not in request.files:
        return jsonify({'success': False, 'message': 'Nenhum arquivo PDF enviado.'}), 400
    
    file = request.files['pdf_file']
    paginas_str = request.form.get('pages')
    modelo_escolhido = request.form.get('model_type')

    if not all([file, paginas_str, modelo_escolhido]):
        return jsonify({'success': False, 'message': 'Dados insuficientes.'}), 400
        
    # Extrai a tabela bruta do PDF
    df_bruto = extrair_tabelas_camelot_stream(file, paginas_str)
    
    if df_bruto is None or df_bruto.empty:
        return jsonify({'success': False, 'message': 'Falha na extração. Nenhuma tabela encontrada.'}), 500

    # --- MODO DIAGNÓSTICO ---
    # Em vez de limpar, vamos salvar a saída bruta para análise.
    print("MODO DIAGNÓSTICO ATIVADO: Gerando a saída bruta do Camelot...")
    
    buffer = io.BytesIO()
    # Salva o DataFrame bruto, com cabeçalhos e índice, para vermos a estrutura completa
    df_bruto.to_csv(buffer, index=True, header=True, sep=';', encoding='latin-1')
    buffer.seek(0)

    nome_arquivo_saida = f"DEBUG_SAIDA_BRUTA_{modelo_escolhido}.csv"

    return send_file(
        buffer,
        as_attachment=True,
        download_name=nome_arquivo_saida,
        mimetype='text/csv'
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
