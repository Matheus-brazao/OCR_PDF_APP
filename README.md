# OCR PDF App



Ferramenta para transformar PDFs escaneados em:

- Arquivos TXT

- PDFs pesquisáveis
- Relatórios de confiança do OCR (JSON e CSV)



## 🚀 Requisitos

- Python 3.10+

- \[Tesseract OCR](https://github.com/tesseract-ocr/tesseract) instalado  

&nbsp; (colocar o caminho no `ocr\_pdf\_app.py` em `pytesseract.pytesseract.tesseract\_cmd`)

- Arquivos de idioma (`eng.traineddata`, `por.traineddata`) na pasta `tessdata`



## 📦 Instalação

Clone este repositório ou baixe os arquivos.



Instale as dependências:

``bash

pip install -r requirements.txt``



# Uso



### Linha de comando (modo profissional)



`python ocr\_pdf\_app.py "C:\\Users\\...\\arquivo.pdf" --outdir out --langs por+eng`



### Duplo clique (modo usuário final)



- Basta dar duplo clique em `ocr\_pdf\_app.py` (ou no `.exe`, se empacotado).

&nbsp; 

- O programa abre uma janela para escolher o PDF.

&nbsp; 



## Saídas



- `out/nome\_arquivo.txt` → texto extraído

&nbsp; 

- `out/nome\_arquivo\_searchable.pdf` → PDF pesquisável

&nbsp; 

\- `out/nome\_arquivo\_ocr\_report.json` → métricas detalhadas

&nbsp; 

\- `out/nome\_arquivo\_ocr\_report.csv` → resumo em CSV

