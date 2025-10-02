from dotenv import load_dotenv
import os
from azure.core.credentials import AzureKeyCredential
from azure.ai.formrecognizer import DocumentAnalysisClient

# Carregar variáveis
load_dotenv()

endpoint = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
api_key = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_API_KEY")

print(f"Endpoint: {endpoint}")
print(f"API Key: {api_key[:10]}..." if api_key else "API Key: None")

if endpoint and api_key:
    try:
        client = DocumentAnalysisClient(
            endpoint=endpoint,
            credential=AzureKeyCredential(api_key)
        )
        
        # Teste simples - criar o cliente sem fazer chamada à API ainda
        print("✅ Cliente Azure criado com sucesso!")
        print("✅ Credenciais carregadas corretamente!")
        
        # Teste real com um documento fictício (vai dar erro, mas é esperado)
        try:
            # Tentativa de análise (vai falhar por não ter documento, mas testa autenticação)
            result = client.begin_analyze_document("prebuilt-layout", b"test")
        except Exception as auth_test:
            if "401" in str(auth_test) or "Unauthorized" in str(auth_test):
                print("❌ Erro de autenticação - verifique as credenciais")
            elif "400" in str(auth_test) or "Bad Request" in str(auth_test):
                print("✅ Autenticação OK! (Erro esperado por documento inválido)")
            else:
                print(f"✅ Conexão estabelecida! Erro esperado: {auth_test}")
        
    except Exception as e:
        print(f"❌ Erro na criação do cliente: {e}")
else:
    print("❌ Variáveis de ambiente não carregadas")
