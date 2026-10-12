# colibre

colibre est une plateforme permettant d'explorer, filtrer et visualiser les données des marchés publics
français. Elle est alimentée par des données publiées en Open Data et propose également une API REST JSON
ainsi qu'un connecteur MCP, les deux accessibles via des abonnements distincts.

## Schéma des données

Le schéma des données est au format TableSchema et peut être librement téléchargé à cette adresse : <https://www.data.gouv.fr/api/1/datasets/r/9a4144c0-ee44-4dec-bee5-bbef38191d9a>

## Données source

Les données sont publiées en Open Data aux formats Parquet et CSV :

- Parquet : <https://www.data.gouv.fr/api/1/datasets/r/11cea8e8-df3e-4ed1-932b-781e2635e432>
- CSV : <https://www.data.gouv.fr/api/1/datasets/r/22847056-61df-452d-837d-8b8ceadbfc52>

## Connecteur MCP

Les abonné·es à colibre peuvent utiliser une série d'outils pour agents IA via le connecteur MCP, exposé à l'adresse <https://colibre.fr/_mcp>. L'abonnement peut se faire depuis [cette page](https://colibre.fr/projet/abonnement).

## API

L'API nécessite un jeton d'authentification pour se connecter, accessible via un abonnement spécifique. [Envoyez un message](https://colibre.fr/a-propos/contact) si vous souhaitez souscrire à un abonnement API. L'API utilise le même schéma que les données et renvoie les données au format JSON.

- Point d'accès : <https://colibre.fr/api/v1/data>
- Spec Open API/Swagger : <https://colibre.fr/api/v1/openapi.json>
- Health : <https://colibre.fr/api/v1/health>

## Sources de données

Les données proviennent de nombreuses sources de données, le projet publie des statistiques au format CSV : <https://www.data.gouv.fr/api/1/datasets/r/8ded94de-3b80-4840-a5bb-7faad1c9c234>
