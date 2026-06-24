import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import urljoin
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://g1.globo.com"

HEADERS = {"User-Agent": "Mozilla/5.0"}
SECTION_URLS = {
    "Tecnologia": f"{BASE_URL}/tecnologia/",
    "Economia": f"{BASE_URL}/economia/",
    "Politica": f"{BASE_URL}/politica/",
}
RESEARCH_LINKS = {
    "G1": {
        "Tecnologia": "https://g1.globo.com/tecnologia/",
        "Economia": "https://g1.globo.com/economia/",
        "Politica": "https://g1.globo.com/politica/",
    },
    "R7": {
        "Tecnologia": "https://noticias.r7.com/tecnologia-e-ciencia",
        "Economia": "https://noticias.r7.com/economia",
        "Politica": "https://noticias.r7.com/politica",
    },
    "BandNews": {
        "Tecnologia": "https://www.band.uol.com.br/noticias/tecnologia",
        "Economia": "https://www.band.uol.com.br/noticias/economia",
        "Politica": "https://www.band.uol.com.br/noticias/politica",
    },
}


def load_env_file():
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and value and key not in os.environ:
            os.environ[key] = value


load_env_file()

def fetch_article_description(url):
    article_response = requests.get(url, headers=HEADERS, timeout=20)
    article_response.raise_for_status()

    article_soup = BeautifulSoup(article_response.text, "html.parser")
    description_tag = article_soup.find("meta", attrs={"property": "og:description"})
    if description_tag is None:
        description_tag = article_soup.find("meta", attrs={"name": "description"})

    return description_tag.get("content", "").strip() if description_tag else ""


def scrape_section_news(section_name, section_url, limit=5):
    """Extrai as notícias mais recentes de uma seção do G1"""
    try:
        response = requests.get(section_url, headers=HEADERS, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        news_items = []
        seen_links = set()

        for post in soup.select(".feed-post"):
            title_tag = post.select_one("h2") or post.select_one(".feed-post-body-title")
            link_tag = post.select_one("a[href]")

            if not title_tag or not link_tag:
                continue

            link = urljoin(BASE_URL, link_tag.get("href"))
            if link in seen_links:
                continue

            seen_links.add(link)
            title = title_tag.get_text(" ", strip=True)
            description = fetch_article_description(link)

            news_items.append({
                "title": title,
                "link": link,
                "description": description,
            })

            if len(news_items) >= limit:
                break

        if not news_items:
            raise ValueError(f"Nenhuma notícia encontrada na seção {section_name}")

        return news_items
    except Exception as e:
        print(f"Erro ao acessar G1 ({section_name}): {e}")
        return []


def scrape_g1_news():
    """Extrai as 5 notícias mais recentes de cada seção"""
    news_by_section = {}
    for section_name, section_url in SECTION_URLS.items():
        news_by_section[section_name] = scrape_section_news(section_name, section_url, limit=5)
    return news_by_section

def send_email(news_by_section):
    """Envia a notícia para o email"""
    try:
        sender_email = os.getenv("SMTP_USER")
        sender_password = os.getenv("SMTP_APP_PASSWORD")
        receiver_email = os.getenv("SMTP_TO_EMAIL")
        cc_email = os.getenv("SMTP_CC_EMAIL", "mateus.estevam@sfa.adv.br")

        if not sender_email or not sender_password or not receiver_email:
            raise ValueError("Defina SMTP_USER, SMTP_APP_PASSWORD e SMTP_TO_EMAIL no ambiente")
        
        message = MIMEMultipart()
        message["From"] = sender_email
        message["To"] = receiver_email
        message["Cc"] = cc_email
        message["Subject"] = "Top 5 notícias do G1: Tecnologia, Economia e Política"

        sections_html = []
        for section_name, news_items in news_by_section.items():
            items_html = []
            for index, news in enumerate(news_items, start=1):
                items_html.append(
                    f"<li><strong>{index}. {news['title']}</strong><br>"
                    f"{news['description']}<br>"
                    f"<a href=\"{news['link']}\">Leia mais</a></li>"
                )

            sections_html.append(
                f"<h2>{section_name}</h2><ol>{''.join(items_html)}</ol>"
            )

        research_links_html = []
        for portal_name, links_by_section in RESEARCH_LINKS.items():
            portal_items = []
            for section_name, link in links_by_section.items():
                portal_items.append(f"<li><a href=\"{link}\">{section_name}</a></li>")
            research_links_html.append(f"<h3>{portal_name}</h3><ul>{''.join(portal_items)}</ul>")

        body = f"""
        <html>
            <body>
                <h1>Top 5 notícias do G1</h1>
                {''.join(sections_html)}
                <h2>Links de pesquisa</h2>
                {''.join(research_links_html)}
            </body>
        </html>
        """
        
        message.attach(MIMEText(body, "html"))

        recipients = [receiver_email]
        if cc_email:
            recipients.extend([email.strip() for email in cc_email.split(",") if email.strip()])
        
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipients, message.as_string())
        
        print("Email enviado com sucesso!")
    except Exception as e:
        print(f"Erro ao enviar email: {e}")

def main():
    """Função principal"""
    print("Iniciando automação...")
    news_by_section = scrape_g1_news()
    
    if any(news_by_section.values()):
        for section_name, news_items in news_by_section.items():
            print(f"{section_name}: {len(news_items)} notícias encontradas")
        send_email(news_by_section)
    else:
        print("Falha ao extrair notícias")

if __name__ == "__main__":
    main()
