# Internal Template Test Fixture

The source internal template is not committed to Git. Set `BILU_TEMPLATE_PATH`
to its local DOCX path when running the optional integration regression:

```powershell
$env:BILU_TEMPLATE_PATH = 'C:\path\to\询问笔录模版.docx'
backend\.venv\Scripts\python.exe -m pytest -q backend\tests\test_template_document_parser.py
```

The mandatory regression constructs a synthetic DOCX with the same failure
shape: readable document XML and a corrupt nonessential image member.

