import os
import re
import camelot
import pandas as pd
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS # Importar CORS

# --- Configuração do Servidor Flask ---
app = Flask(__name__)
# A linha abaixo é a mais importante: permite requisições do seu app React
CORS(app) 

# --- Configuração das Pastas ---
PASTA_ENTRADA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'documentos_entrada')
PASTA_SAIDA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'documentos_saida')
os.makedirs(PASTA_ENTRADA, exist_ok=True)
os.makedirs(PASTA_SAIDA, exist_ok=True)

# --- SUAS FUNÇÕES ORIGINAIS (sem alterações) ---
def extrair_tabela_com_camelot(caminho_pdf, paginas_str):
    # ... (código da função igual ao anterior) ...
    print(f"Iniciando extração com Camelot (modo STREAM) nas páginas: {paginas_str}...")
    try:
        tabelas = camelot.read_pdf(caminho_pdf, pages=paginas_str, flavor='stream', row_tol=10)
    except Exception as e:
        print(f"Ocorreu um erro ao ler o PDF com Camelot: {e}")
        return None
    if not tabelas:
        print("Nenhuma tabela foi detectada pelo Camelot no modo 'stream'.")
        return None
    print(f"SUCESSO NA EXTRAÇÃO! Foram detectadas {len(tabelas)} tabelas.")
    return pd.concat([tabela.df for tabela in tabelas], ignore_index=True)

def limpar_dataframe_final(df_bruto):
    # ... (código da função igual ao anterior) ...
    df = df_bruto.copy()
    df.columns = range(df.shape[1])
    header_row_index = -1
    for i, row in df.iterrows():
        if row.astype(str).str.contains("Marcação").any():
            header_row_index = i
            break
    if header_row_index == -1: header_row_index = 0

    header_series = df.iloc[header_row_index].astype(str)
    col_inicio, col_fim = -1, -1
    for i, cell in header_series.items():
        if "Dia" in cell: col_inicio = i
        if "FALTAS" in cell:
            col_fim = i
            break
    if col_inicio == -1 or col_fim == -1: col_inicio, col_fim = 0, 3

    df_relevante = df.iloc[:, col_inicio:col_fim]
    linhas_completas = df_relevante.apply(lambda row: ' '.join(row.astype(str)), axis=1)

    dados_limpos = []
    for linha_texto in linhas_completas:
        match_linha = re.search(r"(\d{2}/\d{2}/\d{4})\s+\w{3}-\w+", linha_texto)
        if match_linha:
            data = re.search(r"(\d{2}/\d{2}/\d{4})", match_linha.group(1)).group(1)
            horarios = re.findall(r'(\d{2}:\d{2})', linha_texto)
            horarios.extend([0] * (4 - len(horarios)))
            dados_limpos.append({'Data': data, 'Entrada1': horarios[0], 'Saida1': horarios[1], 'Entrada2': horarios[2], 'Saida2': horarios[3]})
            
    if not dados_limpos: return pd.DataFrame()
    return pd.DataFrame(dados_limpos)

# --- ROTAS DA API ---
# Note que os nomes das rotas são os mesmos, mas elas agora só retornam dados (JSON)

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'pdf_file' not in request.files:
        return jsonify({'success': False, 'message': 'Nenhum arquivo enviado.'}), 400
    file = request.files['pdf_file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Nenhum arquivo selecionado.'}), 400
    if file and file.filename.endswith('.pdf'):
        filename = file.filename
        caminho_salvo = os.path.join(PASTA_ENTRADA, filename)
        file.save(caminho_salvo)
        return jsonify({'success': True, 'filename': filename})
    else:
        return jsonify({'success': False, 'message': 'Arquivo inválido. Por favor, envie um PDF.'}), 400

@app.route('/process', methods=['POST'])
def process_file():
    data = request.get_json()
    nome_arquivo_pdf = data.get('filename')
    paginas_str = data.get('pages', 'all')
    if not nome_arquivo_pdf:
        return jsonify({'success': False, 'message': 'Nome do arquivo não fornecido.'}), 400
    
    caminho_completo_pdf = os.path.join(PASTA_ENTRADA, nome_arquivo_pdf)
    df_bruto = extrair_tabela_com_camelot(caminho_completo_pdf, paginas_str)
    if df_bruto is None or df_bruto.empty:
        return jsonify({'success': False, 'message': 'Falha na extração. Nenhuma tabela encontrada.'}), 500

    df_limpo = limpar_dataframe_final(df_bruto)
    if df_limpo.empty:
        return jsonify({'success': False, 'message': 'Não foi possível limpar ou formatar os dados.'}), 500

    ordem_colunas = ['Data', 'Entrada1', 'Saida1', 'Entrada2', 'Saida2']
    df_final = df_limpo.reindex(columns=ordem_colunas, fill_value=0)
    
    nome_base = os.path.splitext(nome_arquivo_pdf)[0]
    nome_arquivo_saida = f"resultado_{nome_base}_pag_{paginas_str.replace('-', '_')}.xlsx"
    caminho_arquivo_saida = os.path.join(PASTA_SAIDA, nome_arquivo_saida)
    df_final.to_excel(caminho_arquivo_saida, index=False)
    
    return jsonify({'success': True, 'download_filename': nome_arquivo_saida})

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(PASTA_SAIDA, filename, as_attachment=True)

if __name__ == "__main__":
    # Roda a API na porta 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
