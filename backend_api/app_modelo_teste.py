import camelot
import pandas as pd
import io
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# --- Configuração do Servidor Flask para o modo de teste ---
app = Flask(__name__)
CORS(app)

# Para evitar que o pandas corte a exibição das colunas no terminal
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)
pd.set_option('display.max_rows', None)

@app.route('/process', methods=['POST'])
def process_file_for_test():
    if 'pdf_file' not in request.files:
        return jsonify({'success': False, 'message': 'Nenhum arquivo PDF enviado.'}), 400

    file = request.files['pdf_file']
    paginas_str = request.form.get('pages', 'all')

    # Cria um buffer de string para armazenar os resultados
    output_buffer = io.StringIO()

    output_buffer.write(f"--- Iniciando extração do arquivo '{file.filename}' nas páginas '{paginas_str}' ---\n")

    # --- MODO LATTICE ---
    try:
        output_buffer.write("\n\n--- TENTANDO EXTRAÇÃO COM O MODO 'LATTICE' ---\n")
        # A imagem de exemplo usa o flavor 'lattice' para tabelas com linhas claras
        lattice_tables = camelot.read_pdf(
            file,
            pages=paginas_str,
            flavor='lattice',
            suppress_stdout=True # Suprime a saída do camelot no console do servidor
        )

        if lattice_tables.n > 0:
            output_buffer.write(f"\n[SUCESSO] O modo 'LATTICE' encontrou {lattice_tables.n} tabela(s).\n")
            for i, table in enumerate(lattice_tables):
                output_buffer.write(f"\n--- Tabela LATTICE [{i+1}] ---\n")
                output_buffer.write(table.df.to_string())
                output_buffer.write("\n" + "-" * 30 + "\n")
        else:
            output_buffer.write("\n[INFO] O modo 'LATTICE' não encontrou tabelas com grades claras.\n")

    except Exception as e:
        output_buffer.write(f"\n[ERRO] Ocorreu um erro ao tentar usar o modo 'LATTICE': {e}\n")


    # --- MODO STREAM ---
    try:
        output_buffer.write("\n\n--- TENTANDO EXTRAÇÃO COM O MODO 'STREAM' ---\n")
        # A imagem de exemplo também demonstra o uso do flavor 'stream'
        stream_tables = camelot.read_pdf(
            file,
            pages=paginas_str,
            flavor='stream',
            suppress_stdout=True
        )

        if stream_tables.n > 0:
            output_buffer.write(f"\n[SUCESSO] O modo 'STREAM' encontrou {stream_tables.n} tabela(s).\n")
            for i, table in enumerate(stream_tables):
                output_buffer.write(f"\n--- Tabela STREAM [{i+1}] ---\n")
                output_buffer.write(table.df.to_string())
                output_buffer.write("\n" + "-" * 30 + "\n")
        else:
            output_buffer.write("\n[INFO] O modo 'STREAM' não encontrou tabelas.\n")

    except Exception as e:
        output_buffer.write(f"\n[ERRO] Ocorreu um erro ao tentar usar o modo 'STREAM': {e}\n")


    output_buffer.write("\n\n--- Fim da análise ---")

    # Prepara o buffer para ser enviado como arquivo
    send_buffer = io.BytesIO()
    send_buffer.write(output_buffer.getvalue().encode('utf-8'))
    send_buffer.seek(0)
    output_buffer.close()
    
    nome_arquivo_saida = f"analise_camelot_{file.filename}.txt"

    return send_file(
        send_buffer,
        as_attachment=True,
        download_name=nome_arquivo_saida,
        mimetype='text/plain'
    )

if __name__ == "__main__":
    # Usando a porta 5002 para o servidor de teste
    app.run(host='0.0.0.0', port=5002, debug=True)