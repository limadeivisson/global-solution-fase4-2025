# calcular_features_para_pois.py
import os
import sys
import pandas as pd
import geopandas as gpd
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from shapely.geometry import Point
from typing import List, Tuple, Optional, Dict, Any
import traceback
import gerenciador_db

# --- Constantes ---
CRS_WGS84: str = "EPSG:4326" 
CRS_PROJETADO_POA: str = "EPSG:31982"

# --- CAMINHOS DE ARQUIVO ATUALIZADOS ---
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DATA_RAW_DIR = os.path.join(ROOT_DIR, 'data', 'raw')
DEM_FILE_PATH = os.path.join(DATA_RAW_DIR, "srtm_porto_alegre.tif")
# --- FIM DOS CAMINHOS ATUALIZADOS ---

POIS_DEFINIDOS: List[Dict[str, Any]] = [
    {'nome_poi': 'POI 1 (Praça da Alfândega - centro)', 'longitude': -51.230, 'latitude': -30.030},
    {'nome_poi': 'POI 2 (Morro Santana - leste)',    'longitude': -51.130, 'latitude': -30.050},
    {'nome_poi': 'POI 3 (Gasômetro - próximo ao rio)', 'longitude': -51.240, 'latitude': -30.025},
    {'nome_poi': 'POI 4 (Centro de Eventos PUCRS - mais elevado)', 'longitude': -51.180, 'latitude': -30.058}
]

def _obter_dem_metrico_e_derivados(
    src_dem: rasterio.DatasetReader, 
    target_crs_metric: str
) -> Optional[Tuple[np.ndarray, np.ndarray, np.ndarray, Any, float, float, str, int, int]]:
    """Helper para obter DEM métrico, seus gradientes (gx, gy) e metadados."""
    src_nodata_val = src_dem.nodata
    elevation_array_metric: Optional[np.ndarray] = None
    affine_metric: Optional[Any] = None
    pw_metric: Optional[float] = None
    ph_metric: Optional[float] = None
    crs_metric: Optional[str] = None
    h_metric: Optional[int] = None
    w_metric: Optional[int] = None

    if src_dem.crs.is_geographic:
        dst_crs_obj = rasterio.crs.CRS.from_string(target_crs_metric)
        affine_metric, w_metric, h_metric = calculate_default_transform(
            src_dem.crs, dst_crs_obj, src_dem.width, src_dem.height, *src_dem.bounds
        )
        elevation_array_metric = np.empty((h_metric, w_metric), dtype=np.float32)
        reproject(
            source=rasterio.band(src_dem, 1), destination=elevation_array_metric,
            src_transform=src_dem.transform, src_crs=src_dem.crs,
            dst_transform=affine_metric, dst_crs=dst_crs_obj,
            resampling=Resampling.bilinear, src_nodata=src_nodata_val, dst_nodata=np.nan
        )
        pw_metric = affine_metric.a
        ph_metric = abs(affine_metric.e)
        crs_metric = target_crs_metric
    elif src_dem.crs.is_projected:
        if src_dem.crs.linear_units.lower() != 'metre':
            print(f"AVISO (Helper): Unidades do DEM projetado não são 'metre' ({src_dem.crs.linear_units}).")
        
        elevation_array_metric = src_dem.read(1).astype(np.float32)
        if src_nodata_val is not None:
            elevation_array_metric[elevation_array_metric == src_nodata_val] = np.nan
        
        affine_metric = src_dem.transform
        pw_metric = affine_metric.a
        ph_metric = abs(affine_metric.e)
        crs_metric = src_dem.crs.to_string()
        h_metric = src_dem.height
        w_metric = src_dem.width
    else:
        print(f"ERRO (Helper): CRS do DEM ({src_dem.crs}) não reconhecido.")
        return None

    if pw_metric == 0 or ph_metric == 0 or elevation_array_metric is None:
        print("ERRO (Helper): Resolução do pixel métrico inválida ou array de elevação não gerado.")
        return None
        
    print(f"INFO (Helper): DEM Métrico pronto (Res: {pw_metric:.2f}m x {ph_metric:.2f}m, CRS: {crs_metric})")
    gy, gx = np.gradient(elevation_array_metric, ph_metric, pw_metric)
    
    return elevation_array_metric, gx, gy, affine_metric, pw_metric, ph_metric, crs_metric, h_metric, w_metric


def calcular_features_para_pontos(
    poi_definitions: List[Dict[str, Any]], 
    dem_path: str, 
    target_crs_metric: str = CRS_PROJETADO_POA
) -> Optional[pd.DataFrame]:
    """Calcula slope e curvature para uma lista de POIs."""
    if not os.path.exists(dem_path):
        print(f"ERRO FATAL: DEM '{os.path.basename(dem_path)}' NÃO ENCONTRADO."); return None

    results = []

    try:
        with rasterio.open(dem_path) as src_dem:
            dem_data = _obter_dem_metrico_e_derivados(src_dem, target_crs_metric)
            if dem_data is None:
                print("ERRO: Não foi possível processar o DEM para obter dados métricos e gradientes.")
                return None
            
            elevation_array_metric, gx_metric, gy_metric, affine_metric, \
            pw_metric, ph_metric, crs_metric, h_metric, w_metric = dem_data

            slope_rad = np.arctan(np.hypot(gx_metric, gy_metric))
            slope_deg_raster = np.degrees(slope_rad)
            slope_deg_raster[np.isnan(elevation_array_metric)] = np.nan
            print("INFO: Raster de Declividade (slope) calculado.")

            _ , gxx_metric = np.gradient(gx_metric, ph_metric, pw_metric)
            gyy_metric , _ = np.gradient(gy_metric, ph_metric, pw_metric)
            laplacian_curvature_raster = gxx_metric + gyy_metric
            laplacian_curvature_raster[np.isnan(elevation_array_metric)] = np.nan
            print("INFO: Raster de Curvatura Laplaciana calculado.")

            poi_geoms = [Point(p['longitude'], p['latitude']) for p in poi_definitions]
            gdf_pois_wgs84 = gpd.GeoDataFrame({'nome_poi': [p['nome_poi'] for p in poi_definitions]}, 
                                            geometry=poi_geoms, crs=CRS_WGS84)
            
            gdf_pois_metric = gdf_pois_wgs84.to_crs(crs_metric)
            print(f"INFO: POIs reprojetados para {crs_metric} para extração de features.")

            for index, poi_row in gdf_pois_metric.iterrows():
                nome = gdf_pois_wgs84.loc[index, 'nome_poi']
                point_geom = poi_row.geometry
                slope_val = np.nan
                curvature_val = np.nan
                
                try:
                    col, row = ~affine_metric * (point_geom.x, point_geom.y)
                    row, col = int(round(row)), int(round(col))

                    if 0 <= row < h_metric and 0 <= col < w_metric:
                        s_val = slope_deg_raster[row, col]
                        c_val = laplacian_curvature_raster[row, col]
                        slope_val = float(s_val) if not np.isnan(s_val) else np.nan
                        curvature_val = float(c_val) if not np.isnan(c_val) else np.nan
                    else:
                        print(f"AVISO: POI '{nome}' fora dos limites do raster métrico.")
                except (IndexError, TypeError):
                    print(f"AVISO: Erro de índice ao amostrar raster para POI '{nome}'.")
                
                results.append({
                    'nome_poi': nome,
                    'longitude_original': gdf_pois_wgs84.loc[index].geometry.x,
                    'latitude_original': gdf_pois_wgs84.loc[index].geometry.y,
                    'slope_degrees': slope_val,
                    'curvature_laplacian': curvature_val
                })
        
        return pd.DataFrame(results)

    except Exception as e:
        print(f"ERRO GERAL ao calcular features para POIs: {e}")
        traceback.print_exc()
        return None

def main():
    print("Iniciando script para calcular Slope e Curvature para POIs (Saída: Banco de Dados)...")
    gerenciador_db.inicializar_banco()
    
    df_poi_features = calcular_features_para_pontos(POIS_DEFINIDOS, DEM_FILE_PATH, CRS_PROJETADO_POA)

    if df_poi_features is not None and not df_poi_features.empty:
        print("\n--- Features Calculadas para os POIs ---")
        for index, row in df_poi_features.iterrows():
            print(f"\nPOI: {row['nome_poi']}")
            print(f"  Longitude (WGS84): {row['longitude_original']:.5f}")
            print(f"  Latitude (WGS84): {row['latitude_original']:.5f}")
            print(f"  Slope (Graus): {row['slope_degrees']:.4f}" if pd.notna(row['slope_degrees']) else "  Slope (Graus): N/A")
            print(f"  Curvature (Laplaciana): {row['curvature_laplacian']:.6f}" if pd.notna(row['curvature_laplacian']) else "  Curvature (Laplaciana): N/A")

        conn = gerenciador_db.criar_conexao()
        if conn:
            try:
                gerenciador_db.atualizar_features_pois(conn, df_poi_features)
            finally:
                conn.close()
        
        print("\nFeatures dos POIs salvas/atualizadas no banco de dados.")

    else:
        print("\nNão foi possível calcular as features para os POIs.")

    print("\nScript concluído.")

if __name__ == "__main__":
    main()