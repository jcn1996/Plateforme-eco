/* ==========================================================================
   Agrégats satellitaires mensuels par pays pour l'agent données alternatives (FACULTATIF).

   Script à coller dans l'éditeur de code de Google Earth Engine (code.earthengine.google.com,
   compte gratuit pour un usage non commercial). Il calcule, pour chaque pays et chaque mois :
   - no2      : densité moyenne de NO2 troposphérique (Sentinel-5P TROPOMI, µmol/m²) ;
   - lumieres : radiance nocturne moyenne (NASA Black Marble VNP46A2, nW/cm²/sr).
   puis exporte un CSV « date,pays,indicateur,valeur » vers Google Drive.

   Publier ensuite ce CSV à une adresse lisible sans connexion (par exemple : l'importer dans
   Google Sheets puis Fichier → Partager → Publier sur le Web → CSV) et enregistrer cette adresse
   dans la variable du dépôt SATELLITES_URL (Settings → Secrets and variables → Actions →
   Variables). Sans cette variable, l'agent ignore les sources satellitaires.
   Relancer le script une fois par mois (début de mois) pour ajouter le mois écoulé.
   ========================================================================== */

// Pays (code ISO à 2 lettres → code FIPS utilisé par la couche des frontières LSIB)
var PAYS = {IN: 'IN', ID: 'ID', BR: 'BR', MX: 'MX', TR: 'TU', VN: 'VM', ZA: 'SF', TH: 'TH', EG: 'EG',
            CO: 'CO', CL: 'CI', AR: 'AR', SA: 'SA', AE: 'AE', CN: 'CH'};
var DEBUT = '2019-01-01';  // historique : au moins 3 ans pour les percentiles
var FIN = ee.Date(Date.now()).update(null, null, 1);  // premier jour du mois en cours (mois en cours exclu)

var frontieres = ee.FeatureCollection('USDOS/LSIB_SIMPLE/2017');
var no2 = ee.ImageCollection('COPERNICUS/S5P/OFFL/L3_NO2').select('tropospheric_NO2_column_number_density');
var nuit = ee.ImageCollection('NASA/VIIRS/002/VNP46A2').select('Gap_Filled_DNB_BRDF_Corrected_NTL');

var nbMois = FIN.difference(ee.Date(DEBUT), 'month').round();
var mois = ee.List.sequence(0, nbMois.subtract(1)).map(function (k) { return ee.Date(DEBUT).advance(k, 'month'); });

var lignes = ee.FeatureCollection(ee.List(Object.keys(PAYS)).map(function (iso) {
  var zone = frontieres.filter(ee.Filter.eq('country_co', ee.Dictionary(PAYS).get(iso))).geometry();
  return ee.FeatureCollection(mois.map(function (d) {
    d = ee.Date(d);
    var f = d.advance(1, 'month');
    var vNo2 = no2.filterDate(d, f).mean().multiply(1e6)
      .reduceRegion({reducer: ee.Reducer.mean(), geometry: zone, scale: 7000, maxPixels: 1e10, bestEffort: true})
      .get('tropospheric_NO2_column_number_density');
    var vNuit = nuit.filterDate(d, f).mean()
      .reduceRegion({reducer: ee.Reducer.mean(), geometry: zone, scale: 5000, maxPixels: 1e10, bestEffort: true})
      .get('Gap_Filled_DNB_BRDF_Corrected_NTL');
    var date = d.format('YYYY-MM-01');
    return ee.FeatureCollection([
      ee.Feature(null, {date: date, pays: iso, indicateur: 'no2', valeur: vNo2}),
      ee.Feature(null, {date: date, pays: iso, indicateur: 'lumieres', valeur: vNuit}),
    ]);
  })).flatten();
})).flatten().filter(ee.Filter.notNull(['valeur']));

Export.table.toDrive({
  collection: lignes, description: 'satellites_mensuels', fileFormat: 'CSV',
  selectors: ['date', 'pays', 'indicateur', 'valeur'],
});
