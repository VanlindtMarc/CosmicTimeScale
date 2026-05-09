# Cosmic Time Scale

Cosmic Time Scale est une application de bureau en Python/Tkinter pour explorer l'histoire sur une echelle compressible. Elle permet de placer des evenements et des periodes sur une timeline, puis de transposer de tres longues durees vers des echelles humaines: une journee, une annee, un siecle, un millenaire, une heure, ou une echelle personnalisee.

L'idee centrale est simple: comprendre quand un evenement arrive si toute une periode de reference etait ramenee a une duree familiere. Par exemple, on peut demander ou se situe la naissance de l'ecriture si l'histoire de l'humanite etait ramenee a une annee, ou replacer des evenements contemporains dans une chronologie plus large.

## Fonctionnalites

- Timeline interactive avec zoom, deplacement horizontal, minimap et recentrage.
- Evenements ponctuels et periodes historiques avec descriptions.
- Saisie par date absolue ou par distance temporelle: "il y a X annees", millions d'annees, milliards d'annees, etc.
- Periodes ouvertes, utiles pour les processus encore en cours.
- Groupes thematiques avec couleurs, visibilite, export separe et comptage.
- Glisser-deposer d'evenements ou de periodes entre groupes.
- Copie vers un autre groupe avec `Ctrl` + glisser-deposer.
- Filtrage de la liste par groupe, groupes visibles ou recherche texte.
- Infobulles detaillees au survol des evenements et periodes.
- Import/export au format `.events`, base sur JSON.
- Sauvegarde automatique dans `autosave.events`.
- Echelles predefinies et personnalisees pour comparer des durees tres differentes.
- Mode "temps reel" pour travailler avec des dates calendaires reelles.

## Exemples d'usages

- Construire une frise historique personnelle, scientifique ou geopolitique.
- Comparer des histoires tres longues: cosmos, Terre, evolution, civilisations, histoire contemporaine.
- Visualiser des periodes imbriquees: guerres, dynasties, mouvements politiques, epoques scientifiques.
- Creer des groupes exportables pour partager une chronologie thematique.
- Utiliser la timeline comme support pedagogique pour expliquer les ordres de grandeur temporels.

## Donnees incluses

Le fichier `autosave.events` fourni contient deja une base de travail riche:

- `363` evenements.
- `101` periodes.
- `21` groupes thematiques.

Parmi les groupes deja presents:

- `Astronomie & Cosmos`
- `Geologie & Terre`
- `Evolution biologique`
- `Prehistoire humaine`
- `Civilisations antiques`
- `Moyen Age`
- `Renaissance & Modernite`
- `XXe siecle`
- `XXIe siecle`
- `Scientifiques`
- `Mathematiques`
- `Sciences & Decouvertes`
- `Decouvertes scientifiques`
- `Catastrophes`
- `Israel-Palestine`
- `Microsoft`
- `Apple`
- `Linux`
- `Intelligence artificielle`
- `Famille`

Le groupe `Microsoft`, par exemple, contient une chronologie detaillee autour de MS-DOS, Windows, Office, Office 365, OOXML, les formats `.docx`, `.xlsx`, `.pptx`, et la normalisation `ISO/IEC 29500`.

## Installation

Le projet utilise uniquement Python et Tkinter pour l'interface graphique.

Prerequis recommandes:

- Python 3.10 ou plus recent.
- Tkinter disponible dans l'installation Python.

Sous Windows, Tkinter est generalement inclus avec Python. Sous Linux, il peut etre necessaire d'installer le paquet correspondant, par exemple `python3-tk`.

## Lancement

Depuis le dossier du projet:

```bash
python cosmic_scale.py
```

Le point d'entree est volontairement court:

```python
from cosmic_scale_app.app import main

if __name__ == "__main__":
    main()
```

## Structure du projet

```text
CGPT/
+-- cosmic_scale.py
+-- autosave.events
+-- CosmicScale.spec
+-- cosmic_scale_app/
    +-- app.py
    +-- core/
    |   +-- shared.py
    +-- ui/
        +-- panels.py
        +-- timeline.py
```

Roles principaux:

- `cosmic_scale.py`: point d'entree de l'application.
- `cosmic_scale_app/app.py`: fenetre principale, orchestration de l'interface, import/export, sauvegarde automatique.
- `cosmic_scale_app/core/shared.py`: modeles de donnees, conversions temporelles, formats d'affichage, constantes.
- `cosmic_scale_app/ui/panels.py`: panneaux de saisie, edition, groupes, liste des evenements et periodes.
- `cosmic_scale_app/ui/timeline.py`: canvas interactif, zoom, deplacement, rendu des evenements, periodes, axe et infobulles.
- `autosave.events`: sauvegarde JSON principale.
- `CosmicScale.spec`: configuration PyInstaller pour generer un executable.

## Format des fichiers `.events`

Les fichiers `.events` sont des fichiers JSON. Ils peuvent contenir:

- des parametres d'echelle;
- des groupes;
- des evenements;
- des periodes.

Exemple simplifie:

```json
{
  "version": 4,
  "ref_period": "Big Bang -> aujourd'hui  (13,8 Ga)",
  "target_scale": "1 an  (365 j)",
  "tags": [
    {
      "name": "Astronomie & Cosmos",
      "color": "#58a6ff",
      "visible": true,
      "locked_visible": false
    }
  ],
  "events": [
    {
      "name": "Formation du Soleil",
      "years_ago": 4600000000,
      "absolute_date": null,
      "description": "Naissance du Soleil dans le nuage proto-solaire.",
      "group_name": "Astronomie & Cosmos"
    }
  ],
  "periods": [
    {
      "name": "Cenozoique",
      "years_ago_start": 66000000,
      "years_ago_end": 0,
      "absolute_date_start": null,
      "absolute_date_end": null,
      "is_ongoing": true,
      "description": "Ere des mammiferes et des oiseaux modernes.",
      "group_name": "Geologie & Terre"
    }
  ]
}
```

## Groupes, evenements et periodes

Un evenement represente un point precis dans le temps. Il peut etre defini par:

- une date absolue, comme `2001-10-25T00:00:00.000000`;
- une valeur `years_ago`, utile pour les dates geologiques, biologiques ou cosmologiques.

Une periode represente un intervalle. Elle peut avoir:

- une date de debut;
- une date de fin;
- un etat `is_ongoing` quand la periode continue jusqu'a aujourd'hui.

Un groupe rassemble des evenements et des periodes autour d'un theme. Chaque groupe possede une couleur de base, et les elements du groupe recoivent automatiquement des variantes lisibles de cette couleur.

## Echelles temporelles

Les periodes de reference incluses sont:

- Big Bang vers aujourd'hui: `13,8` milliards d'annees.
- Formation de la Terre vers aujourd'hui: `4,54` milliards d'annees.
- Apparition de la vie vers aujourd'hui: `3,8` milliards d'annees.
- Ere des dinosaures vers aujourd'hui: `252` millions d'annees.
- Homo sapiens vers aujourd'hui: `300 000` ans.
- Periode personnalisee.

Les echelles de sortie incluses sont:

- `1 heure`
- `1 jour`
- `1 an`
- `1 siecle`
- `1 millenaire`
- `temps reel`
- echelle personnalisee

## Compilation en executable

Le fichier `CosmicScale.spec` permet de construire une version executable avec PyInstaller.

Installation de PyInstaller:

```bash
pip install pyinstaller
```

Compilation:

```bash
pyinstaller CosmicScale.spec
```

L'executable genere porte le nom `CosmicScale`.

## Notes

- La sauvegarde automatique ecrit dans `autosave.events`.
- Les imports remplacent ou fusionnent les donnees selon le mode utilise par l'application.
- Le groupe `Non-classes` est le groupe par defaut et reste toujours visible.
- Les donnees calendaires sont conservees en ISO 8601 quand elles existent, afin de recalculer proprement les positions temporelles au chargement.
- Les evenements cosmologiques ou geologiques peuvent rester ancres uniquement sur `years_ago` quand aucune date calendaire n'a de sens.

## Licence

Aucune licence n'est definie pour le moment. Avant une publication publique sur GitHub, ajoutez une licence adaptee au projet.
