# PDF Triage (triagem de PDF)

**Um script pequeno que decide, página por página, o que o assistente de IA pode ler como texto e o que precisa ver como imagem, para que PDFs longos gastem bem menos tokens sem perder assinaturas, carimbos, manuscritos ou fotos.**

[English](README.md) · Relacionados: [AI Office Guardrails](https://github.com/brunolichtnowadv-ui/ai-office-guardrails) · [No Fake Quotes](https://github.com/brunolichtnowadv-ui/no-fake-quotes) · [Risk-Floor Model Routing](https://github.com/brunolichtnowadv-ui/risk-floor-model-routing) · [No Orphan Tabs](https://github.com/brunolichtnowadv-ui/no-orphan-tabs)

---

## Por quê

Ler um PDF longo só como imagem é caro. Ler só como texto é arriscado: assinatura, carimbo, data manuscrita ou foto simplesmente somem. O script classifica as páginas antes, e o assistente lê texto como texto e olha só o que realmente precisa de olho.

Regra que ele segue: **na dúvida, a imagem vai para análise, e nada é descartado sem registro no relatório.**

## Uso

```bash
python3 -I pdf_triage.py "arquivo.pdf" [--out PASTA] [--pages 1-40] [--lang por]
```

Gera, ao lado do PDF ou em `--out`:

- `text.txt`: o texto de cada página, inclusive o texto por OCR das páginas digitalizadas;
- `images/`: recortes (ou páginas inteiras) que precisam ser vistos;
- `report.md`: o que foi decidido em cada página e uma estimativa da economia de tokens.

`--lang` é o código de idioma do Tesseract para as páginas digitalizadas (`eng` por padrão; para documentos em português use `--lang por`).

## O que ele decide

| Conteúdo da página | Tratamento |
|---|---|
| Texto nativo | Lida como texto |
| Digitalizada, OCR bom | Texto do OCR, mais recortes das regiões que o OCR não leu como palavra (carimbos, assinaturas, manuscritos, fotos) |
| Digitalizada, OCR ruim (foto, manuscrito) | Página inteira como imagem |
| Digitalizada, muitas regiões não textuais | Página inteira como imagem, em resolução menor |
| Imagem embutida | Recortada em boa resolução |
| Gráfico vetorial (15 curvas ou mais) | Recorte da área do gráfico |
| Mesma imagem em 3 ou mais páginas (logotipo, brasão, QR code) | Ignorada, com contagem no relatório |
| Imagem decorativa muito pequena | Ignorada, com contagem no relatório |

PDF danificado é reconstruído com o `qpdf`, e a triagem roda sobre a cópia reparada.

## Exemplo

[`examples/make_sample.py`](examples/make_sample.py) gera um `sample.pdf` inventado de quatro páginas (rode `python3 examples/make_sample.py`; precisa do `reportlab`): duas de texto nativo, uma com gráfico vetorial e uma digitalizada com carimbo e rabisco manuscrito. As páginas 1 a 3 têm o mesmo logotipo. O resultado está em [`examples/report.md`](examples/report.md): o logotipo repetido foi ignorado três vezes, a página digitalizada foi lida por OCR, e o carimbo e o rabisco foram recortados para uma pessoa (ou um modelo) olhar.

## Uso com o Claude

Rode como primeiro passo sempre que chegar um PDF longo; depois leia o `text.txt` e abra só os arquivos de `images/`. Uma skill pode transformar isso em regra: "texto como texto, imagem como imagem; na dúvida, olhar a imagem; citação literal de página digitalizada só depois de conferida na imagem". A regra completa está no [AI Office Guardrails](https://github.com/brunolichtnowadv-ui/ai-office-guardrails), seção 5.

## Requisitos

Python 3 com `pdfplumber`, `Pillow`, `numpy` e `scipy`; as ferramentas de linha de comando `pdftoppm` (poppler-utils) e `tesseract` (com o idioma necessário); `qpdf` para arquivos danificados.

## Limitações

- Os limites no topo do arquivo (área da imagem, imagens repetidas, confiança do OCR, tinta fora das palavras, número de curvas) são heurísticas ajustadas em documentos reais de uma prática. Ajuste para a sua.
- Os números de tokens são estimativas (cerca de 3 caracteres por token de texto, cerca de 750 pixels por token de imagem, 2.300 tokens para uma página inteira como imagem). Nos testes do autor com autos reais (não incluídos, por sigilo) o custo de leitura caiu cerca de metade num documento de 8 páginas e cerca de três quartos num de 93. A sua economia depende de quanto do material é texto nativo.
- Ele não entende o conteúdo. Uma tabela dentro de página digitalizada é lida só por OCR; se a tabela importa, olhe a página.
- A qualidade do OCR depende da digitalização e do idioma passado em `--lang`.

## Licença

[MIT](LICENSE)
