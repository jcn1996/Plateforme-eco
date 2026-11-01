#!/usr/bin/env python3
"""
Compose la texture de la Terre utilisée par le globe (assets/terre-2048.jpg et
assets/terre-1024.jpg) à partir de deux images de la NASA (domaine public) :
  - Blue Marble Next Generation, relief et bathymétrie (déc. 2004) :
    https://eoimages.gsfc.nasa.gov/images/imagerecords/73000/73909/world.topo.bathy.200412.3x5400x2700.jpg
  - Black Marble 2012 (lumières nocturnes) :
    https://eoimages.gsfc.nasa.gov/images/imagerecords/79000/79765/dnb_land_ocean_ice.2012.3600x1800.jpg
Rendu « salle de contrôle » : Terre assombrie, océans bleu nuit profond,
relief encore visible, lumières des villes en surimpression.
Usage : python3 outils/composer_texture_terre.py blue_marble.jpg black_marble.jpg assets/
"""
import sys
import numpy as np
from PIL import Image

jour, nuit, sortie = sys.argv[1], sys.argv[2], sys.argv[3]
L, H = 4096, 2048
a = np.asarray(Image.open(jour).convert('RGB').resize((L, H), Image.LANCZOS), dtype=np.float32) / 255
b = np.asarray(Image.open(nuit).convert('L').resize((L, H), Image.LANCZOS), dtype=np.float32) / 255

# Océans : pixels où le bleu domine nettement (bathymétrie de la Blue Marble)
ocean = np.clip((a[..., 2] - np.maximum(a[..., 0], a[..., 1]) - 0.05) * 6, 0, 1)[..., None]

# Terres : assombries et légèrement bleutées, contraste conservé pour le relief
terre = np.power(a, 1.15) * np.array([0.50, 0.56, 0.66])
# Neige et glaces très claires : atténuées pour ne pas éblouir sur fond sombre
clarte = a.mean(axis=2, keepdims=True)
terre = terre * (1 - 0.62 * np.clip((clarte - 0.42) / 0.4, 0, 1))
# Océans : bleu nuit profond, la profondeur reste discernable
prof = a[..., 2:3]
mer = np.array([0.012, 0.035, 0.095]) + prof * np.array([0.02, 0.06, 0.16])
image = terre * (1 - ocean) + mer * ocean

# Lumières des villes (Black Marble) en jaune doré, seulement sur les terres
lumieres = np.clip((b - 0.30) / 0.55, 0, 1)[..., None] * (1 - ocean)
image = image + lumieres * np.array([1.0, 0.78, 0.42]) * 0.9

image = (np.clip(image, 0, 1) * 255).astype(np.uint8)
img = Image.fromarray(image)
for taille in (2048, 1024):
    img.resize((taille, taille // 2), Image.LANCZOS).save(f'{sortie}/terre-{taille}.jpg', quality=84, optimize=True, progressive=True)
print('ok')
