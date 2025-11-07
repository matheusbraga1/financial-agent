from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from typing import List, Dict, Any, Optional
import logging
import re
from html import unescape

from app.core.config import get_settings
from app.utils.retry import retry_database_operation


logger = logging.getLogger(__name__)
settings = get_settings()


class GLPIService:
    def __init__(self):
        self.prefix = settings.glpi_db_prefix
        self._engine: Optional[Engine] = None
        self._connect()

    def _connect(self) -> None:
        try:
            connection_string = (
                f"mysql+pymysql://{settings.glpi_db_user}:{settings.glpi_db_password}"
                f"@{settings.glpi_db_host}:{settings.glpi_db_port}/{settings.glpi_db_name}"
                f"?charset=utf8mb4"
            )

            self._engine = create_engine(
                connection_string,
                pool_size=5,
                max_overflow=10,
                pool_timeout=30,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=False,
            )

            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            logger.info(f"Conectado ao GLPI em {settings.glpi_db_host}")

        except Exception as e:
            logger.error(f"Erro ao conectar no GLPI: {e}")
            raise

    @retry_database_operation(max_attempts=3)
    def get_all_articles(
        self,
        include_private: bool = False,
        min_content_length: int | None = None,
    ) -> List[Dict[str, Any]]:
        min_length = min_content_length or settings.glpi_min_content_length

        logger.info("Extraindo artigos do GLPI...")

        query = f"""
            SELECT 
                kb.id,
                kb.name AS title,
                kb.answer AS content,
                kb.date_creation,
                kb.date_mod,
                kb.is_faq,
                kb.view,
                kbc.completename AS category,
                kbc.id AS category_id
            FROM {self.prefix}knowbaseitems AS kb
            LEFT JOIN {self.prefix}knowbaseitems_knowbaseitemcategories AS kbrel 
                ON kb.id = kbrel.knowbaseitems_id
            LEFT JOIN {self.prefix}knowbaseitemcategories AS kbc 
                ON kbrel.knowbaseitemcategories_id = kbc.id
            WHERE 1=1
        """

        if not include_private:
            query += " AND kb.view > 0"

        query += " ORDER BY kb.date_mod DESC"

        try:
            with self._engine.connect() as conn:
                result = conn.execute(text(query))
                rows = result.fetchall()

            logger.info(f"Encontrados {len(rows)} artigos no GLPI")

            articles: List[Dict[str, Any]] = []
            skipped = 0

            for row in rows:
                article_dict = dict(row._mapping)
                clean_content = self._clean_html(article_dict.get("content") or "")

                if len(clean_content) < min_length:
                    logger.debug(
                        f"Artigo '{article_dict.get('title')}' muito curto ({len(clean_content)} chars), ignorando"
                    )
                    skipped += 1
                    continue

                articles.append(
                    {
                        "id": str(article_dict["id"]),
                        "title": article_dict.get("title") or "Sem título",
                        "content": clean_content,
                        "category": article_dict.get("category") or "Geral",
                        "metadata": {
                            "glpi_id": article_dict["id"],
                            "category_id": article_dict.get("category_id"),
                            "is_faq": bool(article_dict.get("is_faq")),
                            "date_creation": str(article_dict.get("date_creation")),
                            "date_mod": str(article_dict.get("date_mod")),
                            "source": "GLPI",
                            "visibility": "public" if article_dict.get("view", 0) > 0 else "private",
                        },
                    }
                )

            logger.info(f"{len(articles)} artigos válidos extraídos ({skipped} ignorados)")
            return articles

        except Exception as e:
            logger.error(f"Erro ao extrair artigos: {e}")
            raise

    def get_article_by_id(self, article_id: int) -> Optional[Dict[str, Any]]:
        query = f"""
            SELECT 
                kb.id,
                kb.name AS title,
                kb.answer AS content,
                kbc.completename AS category
            FROM {self.prefix}knowbaseitems AS kb
            LEFT JOIN {self.prefix}knowbaseitems_knowbaseitemcategories AS kbrel 
                ON kb.id = kbrel.knowbaseitems_id
            LEFT JOIN {self.prefix}knowbaseitemcategories AS kbc 
                ON kbrel.knowbaseitemcategories_id = kbc.id
            WHERE kb.id = :article_id
        """
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text(query), {"article_id": article_id})
                row = result.fetchone()
                if not row:
                    return None
                data = dict(row._mapping)
                return {
                    "id": str(data["id"]),
                    "title": data.get("title") or "Sem título",
                    "content": self._clean_html(data.get("content") or ""),
                    "category": data.get("category") or "Geral",
                }
        except Exception as e:
            logger.error(f"Erro ao buscar artigo {article_id}: {e}")
            return None

    def get_categories(self) -> List[Dict[str, Any]]:
        query = f"""
        SELECT 
            id,
            name,
            completename,
            level,
            knowbaseitemcategories_id AS parent_id
        FROM {self.prefix}knowbaseitemcategories
        ORDER BY completename
        """

        try:
            with self._engine.connect() as conn:
                result = conn.execute(text(query))
                rows = result.fetchall()

            categories = [dict(row._mapping) for row in rows]
            logger.info(f"Encontradas {len(categories)} categorias")
            return categories

        except Exception as e:
            logger.error(f"Erro ao buscar categorias: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        queries = {
            "total_articles": f"SELECT COUNT(*) as count FROM {self.prefix}knowbaseitems",
            "public_articles": f"SELECT COUNT(*) as count FROM {self.prefix}knowbaseitems WHERE view > 0",
            "faq_articles": f"SELECT COUNT(*) as count FROM {self.prefix}knowbaseitems WHERE is_faq = 1",
            "total_categories": f"SELECT COUNT(*) as count FROM {self.prefix}knowbaseitemcategories",
        }

        stats: Dict[str, Any] = {}
        try:
            with self._engine.connect() as conn:
                for key, q in queries.items():
                    result = conn.execute(text(q))
                    stats[key] = result.fetchone()[0]
            return stats
        except Exception as e:
            logger.error(f"Erro ao buscar estatísticas: {e}")
            return {}

    @staticmethod
    def _clean_html(html_content: str) -> str:
        if not html_content:
            return ""

        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(unescape(html_content), "html.parser")

            for tag in soup(["script", "style", "meta", "link"]):
                tag.decompose()

            # Listas -> uma linha por item com "- "
            for ul in soup.find_all(["ul", "ol"]):
                for li in ul.find_all("li"):
                    li.insert(0, "- ")
                    li.append("\n")

            # Cabeçalhos: quebra de linha e dois pontos
            for i in range(1, 7):
                for h in soup.find_all(f"h{i}"):
                    h.insert(0, "\n")
                    h.append(":\n")

            for p in soup.find_all("p"):
                p.append("\n\n")

            for div in soup.find_all("div"):
                div.append("\n")

            for br in soup.find_all("br"):
                br.replace_with("\n")

            text = soup.get_text()

        except Exception:
            logger.debug("BeautifulSoup não disponível, usando limpeza básica")
            text = unescape(html_content)
            text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
            text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
            text = re.sub(r"<li>", "\n- ", text, flags=re.IGNORECASE)
            text = re.sub(r"<[^>]+>", "", text)

        text = unescape(text)
        text = re.sub(r" +", " ", text)
        text = re.sub(r"\n\n\n+", "\n\n", text)
        text = re.sub(r"\n ", "\n", text)
        return text.strip()

    def test_connection(self) -> bool:
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text("SELECT VERSION()"))
                version = result.fetchone()[0]
                logger.info(f"Conexão OK - MySQL/MariaDB versão: {version}")
                return True
        except Exception as e:
            logger.error(f"Falha na conexão: {e}")
            return False

    def close(self):
        if self._engine:
            self._engine.dispose()
            logger.info("Conexão com GLPI fechada")


glpi_service = GLPIService()

