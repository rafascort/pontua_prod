# /opt/pontua/AutoPonto/backend_api/debug_bbox.py

import os
import sys
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

from google.cloud import documentai_v1 as documentai
from pypdf import PdfReader, PdfWriter


def main():
    if len(sys.argv) < 3:
        print("Uso: python debug_bbox.py <pdf_path> <page_number>")
        sys.exit(1)

    pdf_path    = sys.argv[1]
    page_number = int(sys.argv[2])
    page_idx    = page_number - 1

    project_id   = os.getenv('GOOGLE_CLOUD_PROJECT')
    location     = os.getenv('DOCAI_PROCESSOR_LOCATION')
    processor_id = os.getenv('DOCAI_PROCESSOR_ID')

    print(f"=" * 80)
    print(f"DEBUG BBOX")
    print(f"=" * 80)
    print(f"PDF:         {pdf_path}")
    print(f"Página:      {page_number} (idx {page_idx})")

    reader = PdfReader(pdf_path)
    writer = PdfWriter()
    writer.add_page(reader.pages[page_idx])
    buf = BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    client = documentai.DocumentProcessorServiceClient(
        client_options={"api_endpoint": f"{location}-documentai.googleapis.com"}
    )
    processor_name = client.processor_path(project_id, location, processor_id)
    request = documentai.ProcessRequest(
        name=processor_name,
        raw_document=documentai.RawDocument(
            content=pdf_bytes,
            mime_type="application/pdf"
        )
    )
    print(f"Enviando ao Document AI...")
    result   = client.process_document(request=request)
    doc      = result.document

    rows = [e for e in doc.entities if e.type_.lower() == 'tabela_marcacoes']
    print(f"Total entidades tabela_marcacoes: {len(rows)}")
    print(f"=" * 80)

    for i, ent in enumerate(rows, start=1):
        print(f"\n[Entidade {i}]")
        if ent.properties:
            for prop in ent.properties:
                val = prop.mention_text.strip() if prop.mention_text else "(vazio)"
                print(f"    {prop.type_:20s} = {repr(val)}")

    print(f"\n{'='*80}")
    print(f"FIM")
    print(f"{'='*80}")


if __name__ == '__main__':
    main()
