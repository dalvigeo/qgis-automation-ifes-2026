"""QGIS 3.44+: algoritmo de Processamento para atualizar o atlas da faixa de domínio.

Salve este arquivo na pasta de scripts de Processamento do QGIS e execute o
algoritmo no projeto minicurso_ifes.qgz. As entradas podem ser trocadas na tela.
"""

from pathlib import Path

from qgis import processing
from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsFeature, QgsField, QgsFields,
    QgsProcessing, QgsProcessingAlgorithm, QgsProcessingException,
    QgsProcessingParameterNumber, QgsProcessingParameterVectorLayer,
    QgsProject, QgsProcessingUtils, QgsVectorFileWriter, QgsVectorLayer,
)


class FaixaDeDominio(QgsProcessingAlgorithm):
    CRS = QgsCoordinateReferenceSystem('EPSG:31984')
    ARQUIVO = 'ATLAS_FAIXA_DOMINIO.gpkg'

    def name(self):
        return 'faixa_de_dominio_nativo'

    def displayName(self):
        return 'Faixa de domínio — atualizar atlas'

    def group(self):
        return 'IFES'

    def groupId(self):
        return 'ifes'

    def createInstance(self):
        return FaixaDeDominio()

    def initAlgorithm(self, config=None):
        self.addParameter(QgsProcessingParameterVectorLayer(
            'rodovia_projeto', 'Rodovia projetada',
            [QgsProcessing.TypeVectorLine]))
        self.addParameter(QgsProcessingParameterVectorLayer(
            'imoveis', 'Imóveis atingidos',
            [QgsProcessing.TypeVectorPolygon]))
        self.addParameter(QgsProcessingParameterNumber(
            'largura_faixa_total', 'Largura de cada lado do eixo (m)',
            QgsProcessingParameterNumber.Double, defaultValue=10, minValue=0.001))

    @staticmethod
    def _run(algoritmo, entrada, contexto, retorno, **opcoes):
        """Executa uma ferramenta nativa com saída intermediária temporária."""
        return processing.run(
            algoritmo, {'INPUT': entrada, **opcoes,
                        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT},
            context=contexto, feedback=retorno,
            is_child_algorithm=True)['OUTPUT']

    @staticmethod
    def _camada(resultado, contexto):
        camada = QgsProcessingUtils.mapLayerFromString(resultado, contexto)
        if camada is None or not camada.isValid():
            raise QgsProcessingException('Não foi possível carregar uma etapa intermediária.')
        return camada

    @staticmethod
    def _selecionar(cam, nomes, geometria):
        """Mantém apenas os campos solicitados e recria a chave fid ao gravar."""
        ausentes = [nome for nome in nomes if cam.fields().indexFromName(nome) < 0]
        if ausentes:
            raise QgsProcessingException(
                f'Campos ausentes em {cam.name()}: {", ".join(ausentes)}')
        destino = QgsVectorLayer(f'{geometria}?crs=EPSG:31984', 'resultado', 'memory')
        destino.dataProvider().addAttributes([cam.fields().field(nome) for nome in nomes])
        destino.updateFields()
        lote = []
        for origem in cam.getFeatures():
            feicao = QgsFeature(destino.fields())
            feicao.setGeometry(origem.geometry())
            feicao.setAttributes([origem[nome] for nome in nomes])
            lote.append(feicao)
        if lote and not destino.dataProvider().addFeatures(lote)[0]:
            raise QgsProcessingException('Falha ao preparar as feições para gravação.')
        destino.updateExtents()
        return destino

    def _gravar(self, camada, arquivo, tabela, contexto):
        """Substitui uma tabela do GeoPackage sem apagar as demais tabelas."""
        opcoes = QgsVectorFileWriter.SaveVectorOptions()
        opcoes.driverName = 'GPKG'
        opcoes.layerName = tabela
        opcoes.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
        opcoes.forceMulti = tabela in {
            'RODOVIA_FINAL', 'IMOVEIS_FINAL',
            'FAIXA_DOMINIO_FINAL', 'FAIXA_POR_IMOVEL'}
        erro, mensagem, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
            camada, str(arquivo), contexto.transformContext(), opcoes)
        if erro != QgsVectorFileWriter.NoError:
            raise QgsProcessingException(f'Falha ao gravar {tabela}: {mensagem}')

    def processAlgorithm(self, parameters, context, feedback):
        projeto = QgsProject.instance()
        if not projeto.fileName():
            raise QgsProcessingException('Salve o projeto QGIS antes de executar.')
        pasta = Path(projeto.fileName()).parent
        arquivo = pasta / self.ARQUIVO
        if not arquivo.exists():
            raise QgsProcessingException(f'GeoPackage não encontrado: {arquivo}')

        rodovia = self.parameterAsVectorLayer(parameters, 'rodovia_projeto', context)
        imoveis = self.parameterAsVectorLayer(parameters, 'imoveis', context)
        largura = self.parameterAsDouble(parameters, 'largura_faixa_total', context)
        if not rodovia or not imoveis or largura <= 0:
            raise QgsProcessingException('Informe as duas camadas e uma largura maior que zero.')
        campos_rodovia = ['NOME', 'TIPO_TRECHO']
        campos_imoveis = [f.name() for f in imoveis.fields() if f.name().lower() != 'fid']
        for nome in ['cod_imovel', 'municipio']:
            if nome not in campos_imoveis:
                raise QgsProcessingException(f'Campo obrigatório ausente nos imóveis: {nome}')

        # 1. Reprojetar, ajustar encontros de linha e mesclar trechos conectados.
        linha = self._run('native:reprojectlayer', rodovia, context, feedback,
                          TARGET_CRS=self.CRS)
        linha = self._run('native:snapgeometries', linha, context, feedback,
                          REFERENCE_LAYER=linha, TOLERANCE=5, BEHAVIOR=0)
        linha = self._run('native:mergelines', linha, context, feedback)
        rodovia_final = self._selecionar(
            self._camada(linha, context), campos_rodovia, 'MultiLineString')
        feedback.setProgress(20)
        if feedback.isCanceled():
            return {}

        # 2. Corrigir imóveis e criar a faixa ao redor do eixo da rodovia.
        poligonos = self._run('native:reprojectlayer', imoveis, context, feedback,
                              TARGET_CRS=self.CRS)
        poligonos = self._run('native:fixgeometries', poligonos, context, feedback,
                              METHOD=1)
        imoveis_final = self._selecionar(
            self._camada(poligonos, context), campos_imoveis, 'MultiPolygon')
        faixa = self._run('native:buffer', linha, context, feedback,
                          DISTANCE=largura, SEGMENTS=5, END_CAP_STYLE=1,
                          JOIN_STYLE=0, MITER_LIMIT=2, DISSOLVE=True,
                          SEPARATE_DISJOINT=False)
        # O buffer dissolvido não carrega atributos; preservar as colunas do atlas.
        faixa_final = QgsVectorLayer('MultiPolygon?crs=EPSG:31984', 'faixa', 'memory')
        faixa_final.dataProvider().addAttributes([
            QgsField('NOME', QVariant.String, len=255),
            QgsField('TIPO_TRECHO', QVariant.String, len=80)])
        faixa_final.updateFields()
        etiquetas = {}
        for nome in campos_rodovia:
            distintos = {str(f[nome]) for f in rodovia_final.getFeatures()
                         if f[nome] is not None and str(f[nome]).strip()}
            etiquetas[nome] = next(iter(distintos)) if len(distintos) == 1 else None
        feicoes_faixa = []
        for origem in self._camada(faixa, context).getFeatures():
            feicao = QgsFeature(faixa_final.fields())
            feicao.setGeometry(origem.geometry())
            feicao.setAttributes([etiquetas['NOME'], etiquetas['TIPO_TRECHO']])
            feicoes_faixa.append(feicao)
        if feicoes_faixa and not faixa_final.dataProvider().addFeatures(feicoes_faixa)[0]:
            raise QgsProcessingException('Falha ao preparar a faixa de domínio.')
        faixa_final.updateExtents()
        feedback.setProgress(45)
        if feedback.isCanceled():
            return {}

        # 3. Intersectar a faixa com os imóveis e unir por código do imóvel.
        recorte = self._run('native:clip', poligonos, context, feedback,
                            OVERLAY=faixa)
        unidos = self._run('native:dissolve', recorte, context, feedback,
                           FIELD=['cod_imovel'], SEPARATE_DISJOINT=False)
        unidos_cam = self._camada(unidos, context)
        faixa_por_imovel = self._selecionar(
            unidos_cam, ['cod_imovel', 'municipio'], 'MultiPolygon')
        feedback.setProgress(65)
        if feedback.isCanceled():
            return {}

        # 4. Extrair vértices de cada polígono, com coordenadas no EPSG:31984.
        pontos = self._run('native:extractvertices', unidos, context, feedback)
        origem_pontos = self._camada(pontos, context)
        campos_pontos = ['cod_imovel', 'vertex_index', 'vertex_part',
                         'vertex_part_ring', 'vertex_part_index']
        faltam = [n for n in campos_pontos if origem_pontos.fields().indexFromName(n) < 0]
        if faltam:
            raise QgsProcessingException('Campos de vértice ausentes: ' + ', '.join(faltam))
        vertices = QgsVectorLayer('Point?crs=EPSG:31984', 'vertices', 'memory')
        esquema = QgsFields()
        esquema.append(QgsField('cod_imovel', QVariant.String))
        for nome in campos_pontos[1:]:
            esquema.append(QgsField(nome, QVariant.Int))
        esquema.append(QgsField('E (m)', QVariant.Double))
        esquema.append(QgsField('N (m)', QVariant.Double))
        esquema.append(QgsField('Vertice', QVariant.String, len=80))
        vertices.dataProvider().addAttributes(list(esquema))
        vertices.updateFields()
        registros = list(origem_pontos.getFeatures())
        max_partes = {}
        for f in registros:
            codigo = f['cod_imovel']
            max_partes[codigo] = max(max_partes.get(codigo, 0), f['vertex_part'])
        lote = []
        for f in registros:
            codigo = f['cod_imovel']
            parte = f['vertex_part']
            indice = f['vertex_part_index']
            rotulo = (f'P{parte + 1:02d}-' if max_partes[codigo] > 0 else '')
            rotulo += f'V{indice + 1:02d}'
            ponto = f.geometry().asPoint()
            saida = QgsFeature(vertices.fields())
            saida.setGeometry(f.geometry())
            saida.setAttributes([codigo, f['vertex_index'], parte,
                                 f['vertex_part_ring'], indice,
                                 ponto.x(), ponto.y(), rotulo])
            lote.append(saida)
        if lote and not vertices.dataProvider().addFeatures(lote)[0]:
            raise QgsProcessingException('Falha ao preparar a camada de vértices.')
        vertices.updateExtents()
        feedback.setProgress(85)
        if feedback.isCanceled():
            return {}

        # 5. Atualizar as tabelas que o projeto já usa, mantendo seus nomes.
        camadas = [('RODOVIA_FINAL', rodovia_final),
                   ('IMOVEIS_FINAL', imoveis_final),
                   ('FAIXA_DOMINIO_FINAL', faixa_final),
                   ('FAIXA_POR_IMOVEL', faixa_por_imovel),
                   ('VERTICES_FAIXA', vertices)]
        for tabela, camada in camadas:
            self._gravar(camada, arquivo, tabela, context)
            for atual in projeto.mapLayersByName(tabela):
                if atual.providerType() == 'ogr' and Path(atual.source().split('|')[0]).resolve() == arquivo.resolve():
                    atual.reload()
            feedback.pushInfo(f'{tabela}: {camada.featureCount()} feições.')
        feedback.setProgress(100)
        return {'GPKG': str(arquivo)}
