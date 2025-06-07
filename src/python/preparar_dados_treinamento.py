# preparar_dados_treinamento.py
import geopandas as gpd
from shapely.geometry import Point
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
import os
import sys
import traceback
from typing import List, Tuple, Optional, Any
import gerenciador_db

# --- Constantes de Configuração ---
MIN_LON: float = -51.3
MAX_LON: float = -51.0
MIN_LAT: float = -30.27
MAX_LAT: float = -29.93
CELL_SIZE_LON: float = 0.005
CELL_SIZE_LAT: float = 0.005
CRS_WGS84: str = "EPSG:4326"
CRS_PROJETADO_POA: str = "EPSG:31982"

FLOOD_RASTER_THRESHOLD: int = 0

# --- NOVOS CAMINHOS DE ARQUIVO ---
# Define o diretório raiz do projeto (subindo dois níveis de src/python/)
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATA_RAW_DIR = os.path.join(ROOT_DIR, 'data', 'raw')

DEM_FILE_PATH = os.path.join(DATA_RAW_DIR, "srtm_porto_alegre.tif")
OSM_GPKG_FILE_PATH = os.path.join(DATA_RAW_DIR, "dados_osm_porto_alegre.gpkg")
FLOOD_EXTENT_FILE_PATH = os.path.join(DATA_RAW_DIR, "mancha_inundacao_porto_alegre.tif")
RIOS_LAYER_NAME_GPKG: str = 'dados_osm_porto_alegre_rios_linhas_POA' 
# --- FIM DOS NOVOS CAMINHOS ---


def criar_grid_pontos(
    min_lon: float, max_lon: float, min_lat: float, max_lat: float,
    cell_size_lon: float, cell_size_lat: float, crs: str
) -> gpd.GeoDataFrame:
    # (Função sem alterações)
    longitudes = np.arange(min_lon, max_lon, cell_size_lon)
    latitudes = np.arange(min_lat, max_lat, cell_size_lat)
    grid_points_geom: List[Point] = [Point(lon_val, lat_val) for lat_val in latitudes for lon_val in longitudes]
    gdf = gpd.GeoDataFrame(geometry=grid_points_geom, crs=crs)
    print(f"INFO (Grid): Grid criado com {len(gdf)} pontos.")
    return gdf

def extrair_elevacao_do_dem(
    gdf_points: gpd.GeoDataFrame, dem_path: str
) -> gpd.GeoDataFrame:
    # (Função sem alterações)
    if not os.path.exists(dem_path):
        print(f"ERRO FATAL (Elevação): DEM '{os.path.basename(dem_path)}' NÃO ENCONTRADO em {dem_path}.")
        raise FileNotFoundError(f"Arquivo DEM não encontrado: {dem_path}")
    elevations: List[Optional[float]] = []
    gdf_points_processed = gdf_points.copy()
    try:
        with rasterio.open(dem_path) as src_dem:
            nodata_value_original = src_dem.nodata
            target_crs_gdf = gdf_points_processed.to_crs(src_dem.crs) if gdf_points_processed.crs != src_dem.crs else gdf_points_processed
            for index, point in target_crs_gdf.iterrows():
                try:
                    row, col = src_dem.index(point.geometry.x, point.geometry.y)
                    if 0 <= row < src_dem.height and 0 <= col < src_dem.width:
                        elevation = src_dem.read(1)[row, col]
                        if nodata_value_original is not None and elevation == nodata_value_original:
                            elevations.append(np.nan)
                        else:
                            elevations.append(float(elevation))
                    else: elevations.append(np.nan)
                except (IndexError, TypeError): elevations.append(np.nan)
        gdf_points_processed['elevation'] = elevations
        print("INFO (Elevação): Elevações extraídas.")
        print(f"INFO (Elevação): Pontos com elevação válida: {gdf_points_processed['elevation'].count()}")
    except Exception as e:
        print(f"ERRO (Elevação): {e}"); gdf_points_processed['elevation'] = np.nan
    return gdf_points_processed

def _obter_dem_metrico(src_dem: rasterio.DatasetReader, target_crs_metric: str) -> Tuple[Optional[np.ndarray], Optional[Any], Optional[float], Optional[float], Optional[str], Optional[int], Optional[int]]:
    # (Função sem alterações)
    src_nodata_val = src_dem.nodata
    if src_dem.crs.is_geographic:
        print(f"INFO (Helper DEM Métrico): DEM Original ({src_dem.crs}) é geográfico. Reprojetando para {target_crs_metric}...")
        dst_crs_obj = rasterio.crs.CRS.from_string(target_crs_metric)
        dst_affine, dst_width, dst_height = calculate_default_transform(
            src_dem.crs, dst_crs_obj, src_dem.width, src_dem.height, *src_dem.bounds
        )
        array_metric = np.empty((dst_height, dst_width), dtype=np.float32)
        reproject(
            source=rasterio.band(src_dem, 1), destination=array_metric,
            src_transform=src_dem.transform, src_crs=src_dem.crs,
            dst_transform=dst_affine, dst_crs=dst_crs_obj,
            resampling=Resampling.bilinear, src_nodata=src_nodata_val, dst_nodata=np.nan
        )
        print("INFO (Helper DEM Métrico): Reprojeção concluída.")
        return array_metric, dst_affine, dst_affine.a, abs(dst_affine.e), target_crs_metric, dst_height, dst_width
    elif src_dem.crs.is_projected:
        print(f"INFO (Helper DEM Métrico): DEM Original ({src_dem.crs}) já é projetado.")
        if src_dem.crs.linear_units.lower() != 'metre':
            print(f"AVISO (Helper DEM Métrico): Unidades do DEM projetado não são 'metre' ({src_dem.crs.linear_units}).")
        array_metric = src_dem.read(1).astype(np.float32)
        if src_nodata_val is not None:
            array_metric[array_metric == src_nodata_val] = np.nan
        return array_metric, src_dem.transform, src_dem.transform.a, abs(src_dem.transform.e), src_dem.crs.to_string(), src_dem.height, src_dem.width
    else:
        print(f"ERRO (Helper DEM Métrico): CRS do DEM ({src_dem.crs}) não reconhecido.")
        return None, None, None, None, None, None, None

def calcular_e_extrair_slope(
    gdf_points: gpd.GeoDataFrame, dem_path: str, target_crs_metric: str = CRS_PROJETADO_POA
) -> gpd.GeoDataFrame:
    # (Função sem alterações)
    gdf_points_processed = gdf_points.copy()
    if not os.path.exists(dem_path):
        print(f"ERRO FATAL (Slope): DEM '{os.path.basename(dem_path)}' NÃO ENCONTRADO."); gdf_points_processed['slope'] = np.nan; return gdf_points_processed
    slopes: List[Optional[float]] = []
    try:
        with rasterio.open(dem_path) as src_dem:
            elevation_array_metric, affine_metric, pw_metric, ph_metric, crs_metric, h_metric, w_metric = _obter_dem_metrico(src_dem, target_crs_metric)
            if elevation_array_metric is None or pw_metric is None or ph_metric is None or pw_metric == 0 or ph_metric == 0:
                print("ERRO (Slope): Falha ao obter DEM métrico ou resolução inválida."); gdf_points_processed['slope'] = np.nan; return gdf_points_processed
            print(f"INFO (Slope): Resolução para cálculo - Largura Pixel: {pw_metric:0.2f}m, Altura Pixel: {ph_metric:0.2f}m (CRS: {crs_metric})")
            gy, gx = np.gradient(elevation_array_metric, ph_metric, pw_metric)
            slope_rad = np.arctan(np.hypot(gx, gy))
            slope_deg_raster = np.degrees(slope_rad)
            slope_deg_raster[np.isnan(elevation_array_metric)] = np.nan 
            print("INFO (Slope): Raster de declividade (graus) calculado.")
            target_crs_gdf = gdf_points_processed.to_crs(crs_metric) if gdf_points_processed.crs.to_string().upper() != crs_metric.upper() else gdf_points_processed
            for index, point in target_crs_gdf.iterrows():
                try:
                    col, row = ~affine_metric * (point.geometry.x, point.geometry.y)
                    row, col = int(round(row)), int(round(col))
                    if 0 <= row < h_metric and 0 <= col < w_metric:
                        slope_val = slope_deg_raster[row, col]
                        slopes.append(float(slope_val) if not np.isnan(slope_val) else np.nan)
                    else: slopes.append(np.nan)
                except (IndexError, TypeError): slopes.append(np.nan)
            gdf_points_processed['slope'] = slopes
            print("INFO (Slope): Declividades extraídas."); print(f"INFO (Slope): Pontos com declividade válida: {gdf_points_processed['slope'].count()}")
    except Exception as e: print(f"ERRO (Slope): {e}"); traceback.print_exc(); gdf_points_processed['slope'] = np.nan
    return gdf_points_processed

def calcular_e_extrair_laplacian_curvature(
    gdf_points: gpd.GeoDataFrame, dem_path: str, target_crs_metric: str = CRS_PROJETADO_POA
) -> gpd.GeoDataFrame:
    # (Função sem alterações)
    gdf_points_processed = gdf_points.copy()
    if not os.path.exists(dem_path):
        print(f"ERRO FATAL (Curvatura): DEM '{os.path.basename(dem_path)}' NÃO ENCONTRADO."); gdf_points_processed['curvature'] = np.nan; return gdf_points_processed
    curvatures: List[Optional[float]] = []
    try:
        with rasterio.open(dem_path) as src_dem:
            elevation_array_metric, affine_metric, pw_metric, ph_metric, crs_metric, h_metric, w_metric = _obter_dem_metrico(src_dem, target_crs_metric)
            if elevation_array_metric is None or pw_metric is None or ph_metric is None or pw_metric == 0 or ph_metric == 0:
                print("ERRO (Curvatura): Falha ao obter DEM métrico ou resolução inválida."); gdf_points_processed['curvature'] = np.nan; return gdf_points_processed
            print(f"INFO (Curvatura): Usando DEM métrico (Res: {pw_metric:0.2f}m x {ph_metric:0.2f}m, CRS: {crs_metric}) para curvatura.")
            gy, gx = np.gradient(elevation_array_metric, ph_metric, pw_metric)
            _   , gxx = np.gradient(gx, ph_metric, pw_metric) 
            gyy , _   = np.gradient(gy, ph_metric, pw_metric) 
            laplacian_curvature_raster = gxx + gyy
            laplacian_curvature_raster[np.isnan(elevation_array_metric)] = np.nan 
            print("INFO (Curvatura): Raster de curvatura Laplaciana calculado.")
            target_crs_gdf = gdf_points_processed.to_crs(crs_metric) if gdf_points_processed.crs.to_string().upper() != crs_metric.upper() else gdf_points_processed
            for index, point in target_crs_gdf.iterrows():
                try:
                    col, row = ~affine_metric * (point.geometry.x, point.geometry.y)
                    row, col = int(round(row)), int(round(col))
                    if 0 <= row < h_metric and 0 <= col < w_metric:
                        curv_val = laplacian_curvature_raster[row, col]
                        curvatures.append(float(curv_val) if not np.isnan(curv_val) else np.nan)
                    else: curvatures.append(np.nan)
                except (IndexError, TypeError): curvatures.append(np.nan)
            gdf_points_processed['curvature'] = curvatures
            print("INFO (Curvatura): Curvaturas Laplacianas extraídas.")
            print(f"INFO (Curvatura): Pontos com curvatura válida: {gdf_points_processed['curvature'].count()}")
    except Exception as e: print(f"ERRO (Curvatura): {e}"); traceback.print_exc(); gdf_points_processed['curvature'] = np.nan
    return gdf_points_processed

def calcular_distancia_rios(
    gdf_points: gpd.GeoDataFrame, osm_gpkg_path: str,
    rios_layer_name: str, target_crs_calculo: str
) -> gpd.GeoDataFrame:
    # (Função sem alterações)
    gdf_points_processed = gdf_points.copy()
    if not os.path.exists(osm_gpkg_path):
        print(f"ERRO FATAL (Dist Rios): GeoPackage '{os.path.basename(osm_gpkg_path)}' NÃO ENCONTRADO.")
        raise FileNotFoundError(f"Arquivo GeoPackage OSM não encontrado: {osm_gpkg_path}")
    try:
        rios_gdf = gpd.read_file(osm_gpkg_path, layer=rios_layer_name)
        if rios_gdf.empty: print("AVISO (Dist Rios): Camada de rios vazia."); gdf_points_processed['distance_to_river'] = np.nan; return gdf_points_processed
        rios_gdf = rios_gdf[rios_gdf.geometry.is_valid & rios_gdf.geometry.geom_type.isin(['LineString', 'MultiLineString'])]
        if rios_gdf.empty: print("AVISO (Dist Rios): Nenhuma geometria de rio válida."); gdf_points_processed['distance_to_river'] = np.nan; return gdf_points_processed
        rios_proj = rios_gdf.to_crs(target_crs_calculo)
        gdf_points_proj = gdf_points_processed.to_crs(target_crs_calculo)
        try: unified_rivers_geom = rios_proj.geometry.union_all()
        except AttributeError: unified_rivers_geom = rios_proj.geometry.unary_union
        if not unified_rivers_geom or unified_rivers_geom.is_empty:
            print("AVISO (Dist Rios): Geometria unificada dos rios vazia."); gdf_points_processed['distance_to_river'] = np.nan; return gdf_points_processed
        distances = gdf_points_proj.geometry.distance(unified_rivers_geom)
        gdf_points_processed['distance_to_river'] = distances.to_list() 
        print("INFO (Dist Rios): Distâncias aos rios calculadas.")
        print(f"INFO (Dist Rios): Pontos com distância válida: {gdf_points_processed['distance_to_river'].count()}")
    except Exception as e: print(f"ERRO (Dist Rios): {e}"); gdf_points_processed['distance_to_river'] = np.nan
    return gdf_points_processed

def determinar_status_inundacao(
    gdf_points: gpd.GeoDataFrame, flood_raster_path: str,
    flood_threshold_value: int
) -> gpd.GeoDataFrame:
    # (Função sem alterações)
    gdf_points_processed = gdf_points.copy()
    if not os.path.exists(flood_raster_path):
        print(f"ERRO FATAL (Status Inundação): Raster da mancha '{os.path.basename(flood_raster_path)}' NÃO ENCONTRADO.")
        raise FileNotFoundError(f"Arquivo da mancha de inundação não encontrado: {flood_raster_path}")
    is_flooded_list: List[int] = []
    try:
        with rasterio.open(flood_raster_path) as src_flood:
            target_crs_gdf = gdf_points_processed.to_crs(src_flood.crs) if gdf_points_processed.crs != src_flood.crs else gdf_points_processed
            for index, point in target_crs_gdf.iterrows():
                try:
                    row, col = src_flood.index(point.geometry.x, point.geometry.y)
                    if 0 <= row < src_flood.height and 0 <= col < src_flood.width:
                        pixel_value = src_flood.read(1)[row, col]
                        is_flooded_list.append(1 if pixel_value > flood_threshold_value else 0)
                    else: is_flooded_list.append(0)
                except (IndexError, TypeError): is_flooded_list.append(0)
        gdf_points_processed['is_flooded'] = is_flooded_list
        print("INFO (Status Inundação): Variável alvo 'is_flooded' calculada.")
        print(f"INFO (Status Inundação): Pontos inundados (1): {sum(is_flooded_list)}, Não inundados (0): {len(is_flooded_list) - sum(is_flooded_list)}")
    except Exception as e: print(f"ERRO (Status Inundação): {e}"); gdf_points_processed['is_flooded'] = 0
    return gdf_points_processed

def preparar_e_salvar_dataset_final(gdf_final: gpd.GeoDataFrame) -> None:
    # --- MODIFICADO PARA SALVAR NO BANCO DE DADOS ---
    gdf_to_extract_coords = gdf_final.to_crs(CRS_WGS84)
    df_for_db = gdf_final.copy()
    df_for_db['longitude'] = gdf_to_extract_coords.geometry.x
    df_for_db['latitude'] = gdf_to_extract_coords.geometry.y
    colunas_selecionadas = ['longitude', 'latitude', 'elevation', 'distance_to_river', 'slope', 'curvature', 'is_flooded']
    
    colunas_faltantes = [col for col in colunas_selecionadas if col not in df_for_db.columns]
    if colunas_faltantes:
        print(f"ERRO CRÍTICO (Save): Colunas faltantes: {colunas_faltantes}. Disponíveis: {df_for_db.columns.tolist()}")
        return
        
    training_data = df_for_db[colunas_selecionadas].copy()
    initial_rows = len(training_data)
    training_data.dropna(inplace=True)
    if len(training_data) < initial_rows:
        print(f"INFO (Save): Removidas {initial_rows - len(training_data)} linhas com NaN.")
    if training_data.empty:
        print("ERRO CRÍTICO (Save): Dataset final VAZIO após NaNs."); return
    
    conn = gerenciador_db.criar_conexao()
    if conn:
        try:
            gerenciador_db.inserir_dados_treinamento_em_lote(conn, training_data)
        finally:
            conn.close()
    else:
        print("ERRO FATAL: Não foi possível conectar ao banco de dados para salvar os dados de treinamento.")
    
    print(f"\nINFO (Save): Dados de treinamento salvos no banco de dados.")
    print(f"Primeiras 5 linhas dos dados processados:"); print(training_data.head())
    print(f"INFO (Save): Dataset final: {len(training_data)} linhas, {len(training_data.columns)} colunas.")

def main():
    print("Iniciando script de preparação de dados (Saída: Banco de Dados SQLite)...") 
    gerenciador_db.inicializar_banco()
    
    print(f"INFO (Main): Lendo dados de entrada de: {DATA_RAW_DIR}")
    
    print("\n--- PASSO 1: Criando Grid ---")
    gdf_grid = criar_grid_pontos(MIN_LON, MAX_LON, MIN_LAT, MAX_LAT, CELL_SIZE_LON, CELL_SIZE_LAT, CRS_WGS84)
    
    print("\n--- PASSO 2: Extraindo Elevação ---")
    try: 
        gdf_com_elevacao = extrair_elevacao_do_dem(gdf_grid, DEM_FILE_PATH)
    except FileNotFoundError: return
    
    if 'elevation' not in gdf_com_elevacao.columns or gdf_com_elevacao['elevation'].isnull().all():
        print("ERRO FATAL (Main): Falha na extração de elevação."); return 
    gdf_com_elevacao.dropna(subset=['elevation'], inplace=True)
    if gdf_com_elevacao.empty: print("ERRO FATAL (Main): Grid vazio após dropna de elevação."); return
    print(f"INFO (Main): Grid com {len(gdf_com_elevacao)} pontos após filtro de elevação.")
    
    print("\n--- PASSO 3: Calculando e Extraindo Declividade (Slope) ---")
    gdf_com_slope = calcular_e_extrair_slope(gdf_com_elevacao, DEM_FILE_PATH, target_crs_metric=CRS_PROJETADO_POA)
    if 'slope' not in gdf_com_slope: 
        print("AVISO (Main): Coluna 'slope' não foi criada. Adicionando com NaNs.")
        if not isinstance(gdf_com_slope, gpd.GeoDataFrame):
            gdf_com_slope = gdf_com_elevacao.copy()
        gdf_com_slope['slope'] = np.nan 

    print("\n--- PASSO 4: Calculando e Extraindo Curvatura Laplaciana ---")
    gdf_com_curvature = calcular_e_extrair_laplacian_curvature(gdf_com_slope, DEM_FILE_PATH, target_crs_metric=CRS_PROJETADO_POA)
    if 'curvature' not in gdf_com_curvature:
        print("AVISO (Main): Coluna 'curvature' não foi criada. Adicionando com NaNs.")
        if not isinstance(gdf_com_curvature, gpd.GeoDataFrame):
            gdf_com_curvature = gdf_com_slope.copy()
        gdf_com_curvature['curvature'] = np.nan

    print("\n--- PASSO 5: Calculando Distância aos Rios ---") 
    try: 
        gdf_com_dist_rio = calcular_distancia_rios(gdf_com_curvature, OSM_GPKG_FILE_PATH, RIOS_LAYER_NAME_GPKG, CRS_PROJETADO_POA)
    except FileNotFoundError: return
    
    print("\n--- PASSO 6: Determinando Status de Inundação ---")
    try: 
        gdf_com_inundacao = determinar_status_inundacao(gdf_com_dist_rio, FLOOD_EXTENT_FILE_PATH, FLOOD_RASTER_THRESHOLD)
    except FileNotFoundError: return
    
    print("\n--- PASSO 7: Preparando e Salvando Dataset Final no Banco de Dados ---")
    preparar_e_salvar_dataset_final(gdf_com_inundacao)
    print("\nProcesso de preparação de dados concluído.")

if __name__ == "__main__":
    main()