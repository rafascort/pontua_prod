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

# ==============================================================================
# FUNÇÃO DE LIMPEZA (LÓGICA DE FATIAMENTO)
# ==============================================================================

def limpar_dataframe_modelo_2(df_bruto):
    """
    Lógica que ignora a estrutura de linhas do Camelot e extrai os dados
    com base em padrões no texto completo, resolvendo o problema de dias na mesma linha.
    """
    print("Aplicando regras de limpeza do Modelo 2 (lógica de fatiamento)...")
    
    # Etapa 1: Juntar toda a tabela em um único bloco de texto
    texto_completo = ' '.join(df_bruto.apply(lambda row: ' '.join(row.astype(str)), axis=1))
    
    # Etapa 2: Encontrar o Mês/Ano de referência nesse texto
    meses_map = {'janeiro': '01', 'fevereiro': '02', 'março': '03', 'abril': '04', 'maio': '05', 'junho': '06', 'julho': '07', 'agosto': '08', 'setembro': '09', 'outubro': '10', 'novembro': '11', 'dezembro': '12'}
    match_competencia = re.search(r"Mes/Ano Competencia\s*:\s*(\w+)\s*/\s*(\d{4})", texto_completo, re.IGNORECASE)
    if not match_competencia:
        print("ERRO: Não foi possível encontrar o 'Mes/Ano Competencia' no cabeçalho.")
        return pd.DataFrame()
        
    mes_nome, ano = match_competencia.group(1).lower(), match_competencia.group(2)
    mes = meses_map.get(mes_nome)
    if not mes:
        print(f"ERRO: Mês '{mes_nome}' não reconhecido.")
        return pd.DataFrame()

    # Etapa 3: Encontrar TODAS as ocorrências de dias na tabela
    # O padrão procura por 3 letras (dia da semana), espaço, e uma data (dd/mm/aa)
    ocorrencias_de_dias = re.findall(r"(\w{3}\s+\d{2}/\d{2}/\d{2})", texto_completo)
    
    dados_limpos = []
    # Itera sobre as ocorrências para "fatiar" o texto
    for i, dia_str in enumerate(ocorrencias_de_dias):
        # Define o início do trecho de texto para este dia
        inicio = texto_completo.find(dia_str)
        # Define o fim do trecho (o início do próximo dia, ou o fim do texto)
        fim = -1
        if i + 1 < len(ocorrencias_de_dias):
            fim = texto_completo.find(ocorrencias_de_dias[i+1], inicio)
        
        trecho_do_dia = texto_completo[inicio:fim] if fim != -1 else texto_completo[inicio:]

        # Extrai a data e os horários deste trecho
        dia = re.search(r"(\d{2})/\d{2}/\d{2}", dia_str).group(1)
        data_completa = f"{dia}/{mes}/{ano}"
        
        horarios = re.findall(r'(\d{2}:\d{2})', trecho_do_dia)
        horarios.extend([0] * (4 - len(horarios)))
        
        dados_limpos.append({
            'Data': data_completa,
            'Entrada1': horarios[0],
            'Saida1': horarios[1],
            'Entrada2': horarios[2],
            'Saida2': horarios[3]
        })

    if not dados_limpos: 
        print("Nenhum dado válido foi extraído após a limpeza.")
        return pd.DataFrame()
        
    return pd.DataFrame(dados_limpos)

# ==============================================================================
# ROTA DA API (VOLTANDO AO MODO DE PRODUÇÃO)
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

    df_limpo = limpar_dataframe_modelo_2(df_bruto)
    if df_limpo.empty:
        return jsonify({'success': False, 'message': 'Não foi possível limpar os dados com o modelo selecionado.'}), 500

    dias_semana_map = {0: 'SEG', 1: 'TER', 2: 'QUA', 3: 'QUI', 4: 'SEX', 5: 'SÁB', 6: 'DOM'}
    df_limpo['Data_dt'] = pd.to_datetime(df_limpo['Data'], format='%d/%m/%Y', errors='coerce')
    df_limpo.dropna(subset=['Data_dt'], inplace=True)
    
    df_limpo['DiaSemana'] = df_limpo['Data_dt'].dt.weekday.map(dias_semana_map)

    ordem_colunas_final = ['Data', 'DiaSemana', 'Entrada1', 'Saida1', 'Entrada2', 'Saida2']
    df_final = df_limpo.reindex(columns=ordem_colunas_final, fill_value=0)

    buffer = io.BytesIO()
    df_final.to_csv(buffer, index=False, header=False, sep=';', encoding='utf-8-sig')
    buffer.seek(0)

    nome_base = os.path.splitext(file.filename)[0]
    nome_arquivo_saida = f"resultado_modelo2_{nome_base}_pag_{paginas_str.replace('-', '_')}.csv"

    print(f"Enviando arquivo '{nome_arquivo_saida}' para download direto.")
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=nome_arquivo_saida,
        mimetype='text/csv'
    )

if __name__ == "__main__":
    # Para o modelo 2, usamos uma porta diferente para não ter conflito
    app.run(host='0.0.0.0', port=5001, debug=True)
