#### 3.3.0 (12 octobre 2026)

**Pour les abonné•es**

- Ajout de la possibilité de saisir des requêtes booléennes complexes dans les filtres de colonnes et le champ objet de l'observatoire (ex : "maitrise d'oeuvre" OU archi). Tout est dans le mode d'emplo. Leur fonctionnement est expliqué dans le mode d'emploi de la page [Tableau](https://colibre.fr/tableau).
- Limite du nombre de résultats par page amenée à 200 dans l'API et le connecteur MCP

**Pour tout le monde**

- Ajout d'un aperçu interactif des filtres appliqués au-dessus des tableaux ([#148](https://github.com/colinmaudry/colibre/issues/148))
- Dans les tableaux les filtres sur la colonne Objet sont insensibles à la casse, aux accents et aux ligatures ([#147](https://github.com/colinmaudry/colibre/issues/147))
- Possiblité de télécharger les données filtrées au format Excel jusqu'à 100 000 lignes et au format CSV au-delà
- Utilisation des montants rationalisés au lieu des montants officiels (parfois aberrants) pour faire la somme des marchés dans l'[observatoire](https://colibre.fr/observatoire) ([méthodologie de calcul](https://github.com/ColinMaudry/decp-processing/blob/main/docs/explications_montants_anormaux.md))
- Pour chaque organisme affiché dans un tableau, ajout d'un raccourci permettant de filtrer cet organisme dans la page Tableau ([#146](https://github.com/colinmaudry/colibre/issues/146))

#### 3.2.0

- Possiblité de réordonner les tuiles de l'observatoire (réservé aux abonné·es) ([#107](https://github.com/colinmaudry/colibre/issues/107))
- Mode sombre pour l'interface (réservé aux abonné·es) ([#118](https://github.com/colinmaudry/colibre/issues/118))
- Amélioration de la visibilité des abonnements

#### 3.1.0

- Dans le Tableau, un bouton permet d'afficher les données filtrées du tableau soit sous forme de lignes (mode actuel, par défaut), soit sous forme de visualisations de données (réservé aux abonné·es) ([#137](https://github.com/colinmaudry/colibre/issues/137))
- Sauvegarde automatique de la base de données des utilisateurs et utilisatrices
- Après s'être connecté·e, on est redirigé vers la page où l'on se trouvait et non sur une page par défaut

##### 3.0.7

- les filtres par nom d'acheteur et de titulaire ne sont plus sensibles aux accents ([#138](https://github.com/colinmaudry/colibre/issues/138))
- les liens vers des marchés renvoyés par le connecteur MCP dans l'agent IA est corrigé

##### 3.0.6

- Ajout des méthodes de paiement Apple Pay et Google Pay

##### 3.0.5

- Correction d'un bug dans le processus de paiement
- Le bouton de navigation "Mon compte" devient un menu déroulant
- Correction de plein de petits bugs

##### 3.0.4

- Ajout de la liste des champs et leur description dans [/projet/donnees](https://colibre.fr/projet/donnees#champs)

##### 3.0.3

- démarrer la période d'essai de l'abonennement ne requiert plus un moyen de paiement
- possibilité de voter en période d'essai
- "À propos" => ["Le projet"](https://colibre.fr/projet)
- amélioration de l'interface de test de l'API ([https://colibre.fr/api/v1/swagger])
- bug résolu dans l'observatoire : les filtres sur les considérations sociales et environnementales se cumulent correctement (ET et pas OU)
- les pages acheteur et titulaire ont un lien vers l'observatoire

##### 3.0.2

- blocage et limitations dans le trafic des robots, en particulier ceux de Baidu

##### 3.0.1

- optimisation du contenu généré pour le SEO (index des pages, sitemaps, titres, métadonnées, etc.) ([#128](https://github.com/ColinMaudry/colibre/issues/128))
- correction du nombre de titulaires affiché en page d'accueil

### 3.0.0

**Fonctionnalités par abonnement**

- Abonnement payant à colibre : période d'essai gratuite, souscription et gestion du moyen de paiement, résiliation, historique de facturation ([#90](https://github.com/ColinMaudry/colibre/issues/90))
- Sauvegarde de vues personnalisées (filtres, tris, colonnes) dans la page Tableau ([#95](https://github.com/ColinMaudry/colibre/issues/95))
- Vote pour prioriser les fonctionnalités de la roadmap, réservé aux abonné·es une fois leur période d'essai terminée, avec une page roadmap publique en lecture seule ([#94](https://github.com/ColinMaudry/colibre/issues/94))
- Accès aux données de colibre via un connecteur MCP (Model Context Protocol), pour interroger colibre directement depuis un agent IA (Claude, Mistral, Gemini, Cursor…) ([#111](https://github.com/ColinMaudry/colibre/issues/111))

**Autres améliorations**

- Nouvelle interface de tableau : plus d'options de filtres, plus performante ([#47](https://github.com/ColinMaudry/colibre/issues/47))
- Ajout des codes et libellés NAF des titulaires, affichés sur leur page /titulaire
- Export Excel mis en forme (styles) ([#83](https://github.com/ColinMaudry/colibre/issues/83))
- Chat intégré 💬 pour répondre à vos questions et recueillir vos suggestions en direct ([#120](https://github.com/ColinMaudry/colibre/issues/120))
- Réduction du nombre de colonnes affichées par défaut et ajout de la colonne "Marché" dans la page Tableau ([#84](https://github.com/ColinMaudry/colibre/issues/84))
- Refonte et mise en page pleine largeur de la page À propos
- Ajout des conditions générales d'utilisation (CGU) ([#93](https://github.com/ColinMaudry/colibre/issues/93))
- Amélioration du référencement (sitemaps acheteurs/titulaires)
- Amélioration significative des performances des pages observatoire, acheteur et titulaire
- decp.info devient **colibre** : nouveau nom, nouvelles icônes ([#57](https://github.com/ColinMaudry/colibre/issues/57))

##### 2.8.1 (25 juin 2026)

- Correction du bug dans la création de token d'API

#### 2.8.0 (23 juin 2026)

- Ajout des considérations sociales et environnementales à l'observatoire
- Les filtres textuels dans les vues tableaux ne sont plus sensibles à l'accentuation
- API privée tabulaire sur abonnement (filtres dynamiques, pagination, tri) avec documentation interactive Swagger UI à `/api/v1/swagger` (📨 <colin@colmo.tech> si intéressé)

##### 2.7.9 (9 juin 2026)

- Ajout d'une vue "étapes" (elle sera mieux intégrée dans le site à l'avenir)
- Correction de petites erreurs qui polluent les logs

##### 2.7.8 (18 mai 2026)

- Récupération du schéma de données plus robuste, ne pas dépendre de data.gouv.fr

##### 2.7.7 (11 mai 2026)

- Suppression des mentions sur les profils d'acheteur. Omnikles/Safetender publie via l'API DUME et Klekoon ne publie pas, mais c'est peut-être pas le seul, donc il est préfèrable de supprimer et refaire un tour.

##### 2.7.6 (5 mai 2026)

- Correction du problème de filtre par date dans les tableaux
- Retour des cartes dans les pages acheteur et titulaire
- Possibilité de chercher un SIRET/SIREN avec des espaces dans les champs `SIRET acheteur` et `Identifiant titulaire`

##### 2.7.5 (24 avril 2026)

- Amélioration des permormances de l'observatoire
- Possibilité dans observatoire (champ objet) et tableau (tous champs texte) de soit chercher des mots présents, soit une suite de mot précise (voir mode d'emploi dans Tableau)
- Ajout d'une animation pendant le chargement de la prévisualisation des données de l'observatoire

##### 2.7.4 (22 avril 2026)

- Utilisation élargie de DuckDB au détriment de Polars => bien meilleure perf ([#72](https://github.com/ColinMaudry/colibre/issues/72)

##### 2.7.3 (20 avril 2026)

- Mise en cache des vues tableau par ensemble de filtres et de tris
- Résolution du bug d'écriture du fichier de vérouillage de la base de données

##### 2.7.2 (19 avril 2026)

- Chargement des données depuis une base DuckDB plutôt qu'en mémoire (plus de stabilité) ([#71](https://github.com/ColinMaudry/colibre/issues/71))
- Mise en cache des vue sur l'observatoire pour un chargement plus rapide (remise à zéro quotidienne)
- Correction de bug : la liste de colonnes par défaut est bien appliquée plutôt qu'afficher toutes les colonnes
- Quelques corrections de bugs d'affichage
- Refactorisation des fonctions utilitaire (`utils.py` approchait des 1 000 lignes)

##### 2.7.1 (23 mars 2026)

- Correction du partage de données filtrées entre dashboard et vue des données

#### 2.7.0 (23 mars 2026)

- Remplacement de la page Statistiques par l'observatoire
- Généralisation de la grille dash (`dbc.Row`, `dbc.Col`)
- Ajout de l'histogramme de distances aux pages acheteur et titulaire
- Ajout de la colonne `acheteur_categorie` (commune, État, etc.)

##### 2.6.2 (22 février 2026)

- Correction du téléchargemnent buggé dans /tableau

##### 2.6.1 (17 février 2026)

- Corrections la création des liens canoniques (SEO)

#### 2.6.0 (5 février 2026)

- Suite de la refonte graphique
- Persistence des filtres, des tris et des choix de colonnes sur toutes les pages
- Joli tableau pour choisir les colonnes à afficher
- Meilleure gestion des acheteurs et titulaires absents de la base SIRENE
- Amélioration du SEO (liens canoniques)

##### 2.5.1 (29 janvier 2026)

- Mise en production un peu hâtive ([#67](https://github.com/ColinMaudry/colibre/issues/67), [#68](https://github.com/ColinMaudry/colibre/issues/68))

#### 2.5.0 (29 janvier 2026)

- Refonte graphique et amélioration des textes d'aide
- Amélioration du filtrage du tableau à partir d'une URL
- Renforcement du SEO avec une arborescence permettant l'accès aux marchés et des snippets JSON-LD
- Suppression de la dépendance à Google Fonts grâce à [Bunny Fonts](https://fonts.bunny.net) 🇪🇺 🇸🇮

##### 2.4.1 (22 janvier 2026)

- Meilleure gestion des colonnes absentes du schéma

#### 2.4.0 (22 janvier 2026)

- Site à peu près utilisable sur petit écran (smartphone) ([#63](https://github.com/ColinMaudry/colibre/issues/63))
- Ajout de nouvelles statistiques dans [/statistiques](https://decp.info/statistiques) (stats par année, doublons par source)
- Amélioration du référencement Web (sitemap, titres, descriptions) ([#50](https://github.com/ColinMaudry/colibre/issues/50))
- Possibilité dans les champs non-numériques de filtrer le texte selon son début ou sa fin (`text*` et `*text`)
- Ajout d'une table des matières dans la page [À propos](https://decp.infi/a-propos) ([#36](https://github.com/ColinMaudry/colibre/issues/36))
- Désactivation du bloquage des robot d'agents de LLM (robots.txt)

##### 2.3.1 (16 janvier 2026)

- Les champs absents du [schéma](https://www.data.gouv.fr/datasets/donnees-essentielles-de-la-commande-publique-consolidees-format-tabulaire?resource_id=9a4144c0-ee44-4dec-bee5-bbef38191d9a) sont ignorés pour éviter les erreurs

#### 2.3.0 (24 décembre 2025)

- Possibilité de filtrer, trier etc. dans les vues acheteur et titulaire
- Possibilité de partager les filtres, tris et choix de colonnes via une adresse Web ([exemple](https://decp.info/tableau?filtres=%7Bobjet%7D+icontains+%22d%C3%A9corations+de+no%C3%ABl%22+%26%26+%7BdateNotification%7D+icontains+2025&colonnes=uid%2Cacheteur_id%2Cacheteur_nom%2Ctitulaire_id%2Ctitulaire_nom%2Cobjet%2Cmontant%2CdateNotification%2Cdistance%2Cacheteur_departement_code))
- Possibilité de filtrer une colonne avec plusieurs mots

##### 2.2.3 (4 décembre 2025)

- mise à jour de l'adresse email de contact (colmo.tech)
- message sur l'indisponibilité des données MINEF

##### 2.2.2 (22 novembre 2025)

- Correction d'un bug dans le téléchargement Excel

##### 2.2.1 (15 novembre 2025)

- Le moteur de recherche ignore les tirets ("franche comté" trouve "Bourgogne-Franche-Comté)
- Phrase "tagline" au-dessus du champ de recherche
- Les infos de Contact rebasculent dans À propos
- Police de caractère "Open Sans" généralisée

#### 2.2.0 (13 novembre 2025)

- Moteur de recherche (acheteurs et titulaires) en page d'accueil ([#58](https://github.com/ColinMaudry/colibre/issues/58))
- Top acheteurs / titulaires par montant attribué/remporté (([#55](https://github.com/ColinMaudry/colibre/issues/55)))
- Moins de colonnes affichées par défaut dans Tableau ([#54](https://github.com/ColinMaudry/colibre/issues/54))

##### 2.1.7 (11 novembre 2025)

- Remplacement du formulaire de contact par une adresse email

##### 2.1.6 (15 octobre 2025)

- Stabilisation de la vue marché

##### 2.1.5 (10 octobre 2025)

- réparation des filtres (notamment < > sur les montants)
- remplacement des valeurs "null" dans les tableaux par des cellules vides

##### 2.1.4 (8 octobre 2025)

- possibilité de filtrer sur le champ "Source"
- création automatique d'une release Github quand je push un tag

##### 2.1.3 (4 octobre 2025)

- tentative d'auto-release à chaque création de tag git
- adaptation au format TableSchema

##### 2.1.2 (3 octobre 2025)

- dataframe global plutôt que lazyframe, pour plus de résilience et charger toutes les données en mémoire

##### 2.1.1 (1er octobre 2025)

- ajout d'une section dans À propos sur la qualité et l'exhaustivité des données ([#43](https://github.com/ColinMaudry/colibre/issues/43))
- ajout du nombre de marchés en plus du nombre de lignes dans la vue Tableau

#### 2.1.0 (30 septembre 2025)

- Ajout des vues [acheteur](https://decp.info/acheteurs/24350013900189) ([#28](https://github.com/ColinMaudry/colibre/issues/28)), [titulaire](https://decp.info/titulaires/51903758414786) ([#35](https://github.com/ColinMaudry/colibre/issues/35)) et [marché](https://decp.info/marches/532239472000482025S00004) ([#40](https://github.com/ColinMaudry/colibre/issues/40)) 🔎
- Ajout des balises HTML meta Open Graph et Twitter ([#39](https://github.com/ColinMaudry/colibre/issues/39)) pour de beaux aperçus de liens 🖼️
- Formulaire de contact ([#48](https://github.com/ColinMaudry/colibre/issues/48)) 📨
- Nom de colonnes plus_agréables ([#33](https://github.com/ColinMaudry/colibre/issues/33)) 💅
- Définition des colonnes quand vous passez votre souris sur les en-têtes ([#33](https://github.com/ColinMaudry/colibre/issues/33)) 📖
- Affichage du numéro de version près du logo et lien vers ici 🤓
- Variables globales uniquement en lecture (😁)

##### 2.0.1 (23 septembre 2025)

- Bloquage du bouton de téléchargement si trop de lignes (+ 65000) [#38](https://github.com/ColinMaudry/colibre/issues/38)
- Amélioration du script de déploiement (deploy.sh)
- Meilleures instructions d'installation et lancement
- Coquilles 🐚

### 2.0.0 (23 septembre 2025)

- détails des sources de données
- section "À propos" plus développée
- correction de bugs dans les filtres de la data table

#### 2.0.0-alpha

- Data table fonctionnelle

### 1.5.0 (28/01/2023

- fixation des dépendances Python pour plus de stabilité en cas de réinstallation (Pipfile)

#### 1.4.1 (14/06/2021)

- ajout des traductions des opérations de filtrage à toutes les vues, pas seulement /db/decp

### 1.4.0 (14/06/2021)

- traduction des opérations de filtrage (ex : contains => contient)
- élargissement des menus de filtrage
- correction du titre de la page des notes de versions

### 1.3.0 (03/06/2021)

- utilisation de noms de colonnes plus lisibles dans l'application
- suppression des références à la licence et aux données source sur la page d'accueil
- correction des liens vers le code source
- correction de l'indentation des puces dans les notes de version

### 1.2.0 (28/05/2021)

- ajout d'une page "Notes de version"
- meilleur lien pour la documentation des champs
- déplacement du code de decp.info depuis [ColinMaudry/decp-table-schema-utils](https://github.com/ColinMaudry/decp-table-schema-utils) vers [ColinMaudry/decp.info](https://github.com/ColinMaudry/colibre)

### 1.1.0 (25/05/2021)

- ajout de nouvelles vues :
  - Marchés publics sans leurs titulaires : vue dédiée aux titulaires de marchés avec des données provenant du répertoire SIRENE
  - Données sur les titulaires et géolocalisation : vue sans les titulaires pour analyser les nombres de marchés et les montants
- amélioration de la page d'accueil
- développement de la page "db" avec description des vues et liste des colonnes
- les codes APE sont cliquables
- ajout des mentions légales
- ajout d'un formulatire d'inscription à une lettre d'information
- correction de bugs :
  - correction du format de certaines dates dans les données

### 1.0.0

- publication sur <https://decp.info>
- ajout d'une vue équivalente au format DECP réglementaire
- personnalisation de datasette
- script de conversion quotidien basé sur [dataflows](https://github.com/datahq/dataflows)
