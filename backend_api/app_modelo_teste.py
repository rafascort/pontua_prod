from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import pandas as pd
from io import BytesIO
from datetime import datetime
import random

app = Flask(__name__)
CORS(app)

@app.route('/process', methods=['POST'])
def process_pdf():
    """Endpoint de teste que retorna dados simulados"""
    try:
        pages = request.form.get('pages', '1-5')
        
        # Simular processamento
        print("🧪 MODO TESTE/DEBUG ATIVADO")
        print(f"📄 Páginas solicitadas: {pages}")
        
        # Criar dados de teste realistas
        dados_teste = []
        
        # Simular múltiplas páginas
        if '-' in pages:
            start, end = map(int, pages.split('-'))
            num_paginas = min(end - start + 1, 5)  # Máximo 5 páginas no teste
        else:
            num_paginas = 1
        
        for pagina in range(1, num_paginas + 1):
            # Dados simulados por página
            for dia in range(1, 6):  # 5 dias por página
                dados_teste.append({
                    'Dia': f'{dia:02d}/11/2021',
                    'Marcacao_Ponto': f'{5 + random.randint(0, 2)}:{random.randint(50, 59)} 11:30 12:30 {17 + random.randint(0, 2)}:{random.randint(50, 59)}',
                    'Faltas': 'Folga' if random.random() > 0.8 else '',
                    'AD_NOT': '',
                    'H_E_100': '',
                    'H_E_50': f'00:{random.randint(20, 59)}' if random.random() > 0.7 else '',
                    'H_NEG': '',
                    'COMP_DIA': '',
                    'SALDO': f'{random.randint(7, 9)}:{random.randint(10, 50)}',
                    'Pagina': pagina
                })
        
        df = pd.DataFrame(dados_teste)
        
        # Criar Excel com múltiplas abas
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Separar por página
            for pagina in df['Pagina'].unique():
                df_pagina = df[df['Pagina'] == pagina].copy()
                df_pagina = df_pagina.drop('Pagina', axis=1)  # Remover coluna de página
                df_pagina.to_excel(writer, sheet_name=f'Pagina_{pagina}', index=False)
        
        output.seek(0)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f'TESTE_debug_{timestamp}.xlsx'
        
        print(f"✅ Arquivo de teste gerado: {filename}")
        print(f"📊 {len(dados_teste)} registros simulados")
        
        return send_file(
            BytesIO(output.read()),
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    
    except Exception as e:
        return jsonify({'error': f'Erro no teste: {str(e)}'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'OK',
        'message': 'Servidor de TESTE/DEBUG funcionando',
        'model': 'Teste/Debug'
    })

if __name__ == '__main__':
    print("🧪 Iniciando servidor de TESTE/DEBUG...")
    print("📍 Servidor rodando em: http://127.0.0.1:5002")
    app.run(host='127.0.0.1', port=5002, debug=True)
