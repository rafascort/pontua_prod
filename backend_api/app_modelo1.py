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
# FUNÇÕES DE PROCESSAMENTO PARA O MODELO 1
# ==============================================================================

def extrair_tabelas_camelot_stream(file_object, paginas_str):
    """
    Função genérica que extrai tabelas de um PDF usando o modo 'stream' do Camelot.
    """
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

def limpar_dataframe_modelo_1(df_bruto):
    """
    Função de limpeza especializada para o layout do "Modelo 1" (JBS Ponto).
    """
    print("Aplicando regras de limpeza do Modelo 1...")
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
        if "FALTAS" in cell: col_fim = i; break
    if col_inicio == -1 or col_fim == -1: col_inicio, col_fim = 0, 3

    df_relevante = df.iloc[:, col_inicio:col_fim]
    linhas_completas = df_relevante.apply(lambda row: ' '.join(row.astype(str)), axis=1)

    dados_limpos = []
    for linha_texto in linhas_completas:
        match_linha = re.search(r"(\d{2}/\d{2}/\d{4}\s+\w{3}-\w+)", linha_texto)
        if match_linha:
            data = re.search(r"(\d{2}/\d{2}/\d{4})", match_linha.group(1)).group(1)
            horarios = re.findall(r'(\d{2}:\d{2})', linha_texto)
            horarios.extend([0] * (4 - len(horarios)))
            dados_limpos.append({
                'Data': data, 'Entrada1': horarios[0], 'Saida1': horarios[1], 
                'Entrada2': horarios[2], 'Saida2': horarios[3]
            })
    if not dados_limpos: return pd.DataFrame()
    return pd.DataFrame(dados_limpos)

# ==============================================================================
# ROTA DA API PARA O MODELO 1
# ==============================================================================

@app.route('/process', methods=['POST'])
def process_file_direct():
    if 'pdf_file' not in request.files:
        return jsonify({'success': False, 'message': 'Nenhum arquivo PDF enviado.'}), 400
    
    file = request.files['pdf_file']
    paginas_str = request.form.get('pages')

    if not all([file, paginas_str]):
        return jsonify({'success': False, 'message': 'Dados insuficientes. Forneça pdf_file e pages.'}), 400
        
    df_bruto = extrair_tabelas_camelot_stream(file, paginas_str)
    if df_bruto is None or df_bruto.empty:
        return jsonify({'success': False, 'message': 'Falha na extração. Nenhuma tabela encontrada.'}), 500

    df_limpo = limpar_dataframe_modelo_1(df_bruto)
    if df_limpo.empty:
        return jsonify({'success': False, 'message': 'Não foi possível limpar os dados com o modelo selecionado.'}), 500

    dias_semana_map = {0: 'SEG', 1: 'TER', 2: 'QUA', 3: 'QUI', 4: 'SEX', 5: 'SÁB', 6: 'DOM'}
    df_limpo['Data_dt'] = pd.to_datetime(df_limpo['Data'], format='%d/%m/%Y')
    df_limpo['DiaSemana'] = df_limpo['Data_dt'].dt.weekday.map(dias_semana_map)

    ordem_colunas_final = ['Data', 'DiaSemana', 'Entrada1', 'Saida1', 'Entrada2', 'Saida2']
    df_final = df_limpo.reindex(columns=ordem_colunas_final, fill_value=0)

    buffer = io.BytesIO()
    df_final.to_csv(buffer, index=False, header=False, sep=';', encoding='utf-8-sig')
    buffer.seek(0)

    nome_base = os.path.splitext(file.filename)[0]
    nome_arquivo_saida = f"resultado_modelo1_{nome_base}_pag_{paginas_str.replace('-', '_')}.csv"

    print(f"Enviando arquivo '{nome_arquivo_saida}' para download direto.")
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=nome_arquivo_saida,
        mimetype='text/csv'
    )

if __name__ == "__main__":
    # Para o modelo 1, podemos usar a porta 5000
    app.run(host='0.0.0.0', port=5000, debug=True)
