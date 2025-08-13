# broadlink_to_tuya
## _Mon script de convertion **broadlink_to_tuya.sh**_
_✌️🥖🔆Fait avec amour dans le sud de la France.❤️️🇫🇷🐓_

Juste un script qui permet de convertir des codes de télécommandes encodés en Broadlink vers Tuya.

## Fonctions principales
Réencode un fichier json contenant les clés IR Brodlink pour les rendre compatibles Tuya.  
Spécialement conçu pour [SmartIR](https://github.com/litinoveweedle/SmartIR) avec prise en charge des émeteurs IR **MOES UFO-R11 / ZS06**.  
Vous n'avez qu'à connaître le code de votre télécommande (voir documentation de SmartIR) et indiquer le type [climate, fan, light, media_player] suivi du controller [MQTT - UFOR11].

## Usage ##
1. Doit être installé depuis HAOS.
2. Le plugin [Advanced SSH and Web Terminal](https://github.com/hassio-addons/addon-ssh) doit être installé, activé et fonctionnel.
3. Le plugin HACS [SmartIR - litinoveweedle](https://github.com/litinoveweedle/SmartIR) doit être installé, activé et fonctionnel.
4. Le librairie Python3 doit être installée.
- Pour vérifier : `python3 --version`  
- Pour installer : `apt install python3`
5. Pour installer le script, la commande est :
```
# Crée l'arborescence si elle n’existe pas
mkdir -p /config/scripts/broadlink_to_tuya

# Télécharge le script depuis le lien brut de GitHub
wget -O /config/scripts/broadlink_to_tuya/broadlink_to_tuya_converter.py \
https://raw.githubusercontent.com/Gotcha26/broadlink_to_tuya/main/broadlink_to_tuya_converter.py
```

## Utilisation - Exemple type ##
Depuis la fenêtre de terminal dans HAOS.  
`python3 /config/scripts/broadlink_to_tuya/broadlink_to_tuya_converter.py 1293 --type climate --controller UFOR11`

## Aide ##
Depuis la fenêtre de terminal dans HAOS.  
`/config/scripts/broadlink_to_tuya/broadlink_to_tuya.sh --help`

> Convertisseur de codes Broadlink vers Tuya compressé.
> 
> Fonctionnement :
>   Ce script lit un fichier JSON contenant des commandes IR Broadlink,
>   les encode et les compresse au format Tuya, puis sauvegarde le résultat
>   dans un répertoire sûre de destination.
> 
> Chemins par défaut :
>   Source : /config/custom_components/smartir/codes/\<type\>/\<fichier\>.json
>   Destination : /config/custom_components/smartir/custom_codes/\<type\>/\<fichier\>.json
> 
> Arguments :
>   source_name : Nom du fichier source (suite numérique ou nom complet)
>   dest_name   : Nom du fichier destination (optionnel)
>   --type     : Sous-répertoire commun (climate, fan, light, media_player)
>   --controller : Type de contrôleur supporté (MQTT ou UFOR11)
> 
> Exemple :
>   python3 broadlink_to_tuya.py 1293 --type climate --controller MQTT
> 
> positional arguments:
>   source_name           Nom du fichier source (suite numérique ou nom complet)
>   dest_name             Nom du fichier destination (optionnel, plus souple)
> 
> options:
>   -h, --help            show this help message and exit
>   --type {climate,fan,light,media_player}
>                         Sous-répertoire commun
>   --controller {MQTT,UFOR11}
>                         Type de contrôleur supporté

#### Origine ####
Le script original se trouve à [cette adresse](https://gist.github.com/svyatogor/7839d00303998a9fa37eb48494dd680f?permalink_comment_id=5153002#gistcomment-5153002).
