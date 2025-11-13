**Données en entrée**
=====================

**1\. Données statiques**
-------------------------

*   **Configuration du réseau routier :**
    
    *   Liste des intersections (id, position…)
        
    *   Routes entre intersections (longueur, orientation, capacité…)
        
    *   Paramètres initiaux des feux (état, durée, orientation)
        
*   **Paramètres des véhicules :**
    
    *   Taux d’arrivée des véhicules
        
    *   Vitesse et comportements simplifiés
        
*   **Paramètres de la simulation :**
    
    *   Durée totale
         
    *   Scénario choisi (léger, saturé…)
        
*   **Paramètres de l’agent RL :**
    
    *   Définition de l’espace d’états
        
    *   Définition des actions possibles
        
    *   Algorithme utilisé 
        
        

**2\. Données dynamiques**
--------------------------

*   **État du trafic :**
    
    *   Positions des véhicules
        
    *   Longueur des files d’attente
        
    *   Temps d’attente par voie
        
    *   Occupation des routes
        
*   **État des feux :**
    
    *   Couleur actuelle 
        
    *   Temps depuis le dernier changement
        
*   **Observations fournies à l’agent RL :**
    
    *   Nombre de véhicules par voie
        
    *   Congestion locale
        
    *   Mesures du débit
        

**Données en sortie**
=====================

**1\. Sorties de la simulation**
--------------------------------

*   Positions des véhicules à chaque pas de temps
    
*   Longueur des files d’attente au fil du temps
    
*   Changements d’état des feux
    
*   Logs détaillés :
    
    *   États observés
        
    *   Actions de l’agent RL
        
    *   Récompenses obtenues
        

**2\. Indicateurs de performance**
----------------------------------

*   Temps de trajet moyen
    
*   Longueur moyenne des files d’attente
    
*   Temps d’attente cumulé par intersection
    
*   Débit de véhicules
    
*   Taux de congestion
    

**3\. Sorties visuelles (optionnelles)**
----------------------------------------

*   Graphiques d’évolution :
    
    *   files d’attente
        
    *   temps de trajet
        
    *   récompenses du RL
        
*   Visualisation ou animation du trafic
    
*   Comparaison :
    
    *   Feux statiques vs feux optimisés
        

**4\. Sorties liées à l’agent RL (si on a le temps) à approndir**
----------------------------------

*   Politique apprise :
    
    *   Table Q ou réseau neuronal 
        
*   Courbes d’apprentissage :
    
    *   Récompense moyenne par épisode
        
    *   Convergence de la politique
        
    *   Évolution de l’exploration ε