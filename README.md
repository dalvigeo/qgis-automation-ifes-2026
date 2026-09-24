# QGIS Automation — IFES 2026

Material do minicurso **QGIS: Soluções com Automação de Fluxos de Trabalho**, apresentado na Semana de Ciência e Tecnologia do Ifes Campus Vitória em 2026.

## Conteúdo

- `guide/`: guia e apresentação em HTML, com imagens e recursos disponíveis offline.
- `qgis/minicurso_ifes.qgz`: projeto QGIS.
- `qgis/DADOS.gpkg`: camadas de entrada do exercício.
- `qgis/ATLAS_FAIXA_DOMINIO.gpkg`: camadas usadas no atlas da faixa de domínio.
- `scripts/Faixa_de_dominio_nativo.py`: algoritmo de Processamento para atualizar o atlas.

## Como usar

1. Abra `guide/index.html` no navegador. Para consultar links externos do guia, conecte-se à internet.
2. Abra `qgis/minicurso_ifes.qgz` no QGIS 3.44 ou posterior. Mantenha os dois GeoPackages na mesma pasta do projeto para preservar as referências relativas.
3. Se desejar executar o algoritmo, adicione `scripts/Faixa_de_dominio_nativo.py` aos scripts de Processamento do QGIS. No projeto, selecione as camadas de rodovia projetada e imóveis atingidos e execute **Faixa de domínio — atualizar atlas**. O algoritmo grava resultados em `qgis/ATLAS_FAIXA_DOMINIO.gpkg`; faça uma cópia desse arquivo antes de executar caso precise preservar seu estado original.

O projeto contém uma camada de imagem de satélite que depende de conexão com a internet. O material didático não exige essa conexão para abrir o guia.

## Origem

Este repositório foi montado apenas com os arquivos disponibilizados para o minicurso. Não foi definida uma licença de reutilização para os dados e demais materiais.
