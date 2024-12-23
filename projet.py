from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from langchain_ollama import OllamaLLM
from pytrends.request import TrendReq
from fuzzywuzzy import fuzz
import json
import sqlite3
import os

# Étape 1 : Scraper les liens
def take_links():
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--headless")  # Exécuter sans interface graphique
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")

    # Utilisation de webdriver_manager pour gérer automatiquement le téléchargement de ChromeDriver
    service = Service(ChromeDriverManager().install())  # Télécharge et gère automatiquement ChromeDriver
    driver = webdriver.Chrome(service=service, options=chrome_options)
   
    url = "https://www.lemonde.fr/"
    driver.get(url)
    driver.implicitly_wait(10)
   
    page_content = driver.page_source
    soup = BeautifulSoup(page_content, "html.parser")
   
    liste_liens = []
    elements = soup.find_all("a")
    for element in elements:
        href = element.get("href")
        if href and href.startswith("https://www.lemonde.fr"):
            liste_liens.append(href)
   
    driver.quit()
    return list(set(liste_liens))  # Élimine les doublons

# Étape 2 : Scraper le contenu des articles
def take_articles(lst, limit=10):
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
   
    # Utilisation de webdriver_manager pour gérer automatiquement le téléchargement de ChromeDriver
    service = Service(ChromeDriverManager().install())  # Télécharge et gère automatiquement ChromeDriver
    driver = webdriver.Chrome(service=service, options=chrome_options)
   
    lst_articles = []
    for link in lst[:limit]:  # Limiter le nombre d'articles
        try:
            driver.get(link)
            driver.implicitly_wait(4)
           
            page_content = driver.page_source
            soup = BeautifulSoup(page_content, "html.parser")
            title = soup.find("h1", class_="article__title")
            texte_paragraphs = soup.find_all("p", class_="article__paragraph")
           
            if title and texte_paragraphs:
                article_title = title.get_text(strip=True)
                article_text = " ".join([p.get_text(strip=True) for p in texte_paragraphs])
               
                lst_articles.append({"url": link, "title": article_title, "content": article_text})
       
        except Exception as e:
            print(f"Erreur lors du chargement de {link}: {e}")
   
    driver.quit()
    return lst_articles

# Étape 3 : Récupérer les tendances Google
def get_google_trends():
    try:
        pytrend = TrendReq()
        trends = pytrend.trending_searches(pn="france")
        return trends[0].tolist()
    except Exception as e:
        print(f"Erreur lors de la récupération des tendances : {e}")
        return []

# Étape 4 : Vérifier la correspondance avec les tendances
def match_trends_fuzzy(text, trends, threshold=70):
    for trend in trends:
        if fuzz.partial_ratio(text.lower(), trend.lower()) > threshold:
            return trend
    return None

# Étape 5 : Générer résumés et titres
def generate_summary_and_title(content, summary_prompt, title_prompt):
    try:
        # Instancier le modèle Ollama
        ollama = OllamaLLM(model="llama3.2")
       
        # Générer le résumé à partir du contenu
        summary = ollama.invoke(f"{summary_prompt}\nTexte : {content}").strip()
       
        # Vérifier si le résumé est vide, et si oui, donner un message par défaut
        if not summary:
            summary = "Résumé non disponible."

        # Générer un seul titre basé sur le résumé
        title = ollama.invoke(f"{title_prompt}\nRésumé : {summary}").strip()
       
        # Vérifier si le titre est vide, et si oui, donner un titre par défaut
        if not title:
            title = "Titre généré automatiquement"

        return summary, title
    except Exception as e:
        print(f"Erreur lors de la génération du résumé et du titre : {e}")
        return "", "Erreur de génération"


# Étape 6 : Sauvegarder dans un fichier JSON en ajoutant les nouveaux résumés
def save_summary_to_json(summary_data, output_file="summaries.json"):
    try:
        # Ouvrir le fichier en mode lecture pour charger les données existantes, si le fichier existe
        if os.path.exists(output_file):
            with open(output_file, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        else:
            # Si le fichier n'existe pas, on initialise un tableau vide
            existing_data = []

        # Ajouter le nouveau résumé à la liste existante
        existing_data.append(summary_data)

        # Sauvegarde les données mises à jour dans le fichier JSON
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=4)
       
        print(f"Le résumé a été sauvegardé dans '{output_file}' en ajoutant les nouvelles données.")
    except Exception as e:
        print(f"Erreur lors de la sauvegarde dans le fichier JSON : {e}")

# Étape 7 : Préparer la base de données
def setup_database():
    conn = sqlite3.connect("summaries.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_title TEXT,
            generated_title TEXT,
            summary TEXT,
            trend_match TEXT,
            url TEXT
        )
    """)
    conn.commit()
    return conn

# Pipeline complet
def main_pipeline():
    # Étape 1 : Scraper les liens
    print("Scraping des liens...")
    liste_liens = take_links()
    print(f"{len(liste_liens)} liens trouvés. Extraction des articles...")

    # Étape 2 : Scraper les articles
    articles = take_articles(liste_liens, limit=10)
    if not articles:
        print("Aucun article scrappé.")
        return

    # Étape 3 : Récupérer les tendances Google
    print("Récupération des tendances Google...")
    trends = get_google_trends()
    print(f"Tendances récupérées : {trends}")

    # Étape 4 : Préparer la base de données
    conn = setup_database()
    cursor = conn.cursor()

    # Prompts pour la génération
    summary_prompt = [
        "Résume cet article en moins de 150 mots, en ne gardant que les idées principales, sans aucune introduction ou phrase d'explication."
        "Lis cet article et écris un résumé en tes propres mots. Ne copie aucun passage textuel, mais capture uniquement les idées générales.",
        "Résume l’article suivant en ne mentionnant que les points les plus importants, de manière claire et structurée. Ne conserve pas de détails superflus.",
        "Fournis un résumé objectif des points clés abordés dans cet article, sans inclure d’opinions ni de jugements personnels."
        "Ce résumer doit etre orginal et généré sans plagier l'artcle "
    ]
    title_prompt = "Génère un titre concis et accrocheur basé sur le résumé ci-dessous. Ne propose qu'un seul titre."


    # Étape 5 : Traiter les articles
    print("Traitement des articles...")
    for article in articles:
        trend_match = match_trends_fuzzy(article["title"], trends) or match_trends_fuzzy(article["content"], trends)
        if trend_match:
            summary, generated_title = generate_summary_and_title(article["content"], summary_prompt, title_prompt)
            if summary and generated_title:
                # Sauvegarde dans la base de données
                cursor.execute("""
                    INSERT INTO articles (original_title, generated_title, summary, trend_match, url)
                    VALUES (?, ?, ?, ?, ?)
                """, (article["title"], generated_title, summary, trend_match, article["url"]))
                conn.commit()

                # Sauvegarde dans le fichier JSON avec toutes les informations nécessaires
                summary_data = {
                    "title": generated_title,
                    "summary": summary,
                    "source": article["url"]
                }
                save_summary_to_json(summary_data)
                print(f"Article sauvegardé : {generated_title}")
   
    conn.close()
    print("Pipeline terminé.")

# Lancer le pipeline
if __name__ == "__main__":
    main_pipeline()