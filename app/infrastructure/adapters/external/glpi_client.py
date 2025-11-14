import logging
from typing import List, Dict, Any, Optional
import pymysql
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class GLPIClient:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 3306,
        database: str = "glpi",
        user: str = "glpi",
        password: str = "",
        table_prefix: str = "glpi_",
    ):
        self.config = {
            "host": host,
            "port": port,
            "database": database,
            "user": user,
            "password": password,
            "charset": "utf8mb4",
            "cursorclass": pymysql.cursors.DictCursor,
        }
        self.table_prefix = table_prefix
        
        try:
            with self._get_connection() as conn:
                logger.info(f"GLPIClient conectado: {host}:{port}/{database}")
        except Exception as e:
            logger.error(f"Erro ao conectar ao GLPI: {e}")
            raise
    
    @contextmanager
    def _get_connection(self):
        conn = pymysql.connect(**self.config)
        try:
            yield conn
        finally:
            conn.close()
    
    def fetch_knowledge_base_articles(
        self,
        limit: Optional[int] = None,
        min_content_length: int = 50,
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            
            query = f"""
                SELECT 
                    kb.id,
                    kb.name as title,
                    kb.answer as content,
                    kb.date_creation,
                    kb.date_mod,
                    kb.users_id as author_id,
                    kb.view as view_count,
                    kbt.language
                FROM {self.table_prefix}knowbaseitems kb
                LEFT JOIN {self.table_prefix}knowbaseitemtranslations kbt 
                    ON kb.id = kbt.knowbaseitems_id
                WHERE kb.is_faq = 0
                    AND LENGTH(kb.answer) >= %s
                ORDER BY kb.date_mod DESC
            """
            
            if limit:
                query += f" LIMIT {limit}"
            
            cur.execute(query, (min_content_length,))
            articles = cur.fetchall()
            
            logger.info(f"Buscados {len(articles)} artigos do GLPI")
            
            return articles
    
    def fetch_faq_items(
        self,
        limit: Optional[int] = None,
        min_content_length: int = 50,
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            
            query = f"""
                SELECT 
                    kb.id,
                    kb.name as title,
                    kb.answer as content,
                    kb.date_creation,
                    kb.date_mod,
                    kb.users_id as author_id,
                    kb.view as view_count
                FROM {self.table_prefix}knowbaseitems kb
                WHERE kb.is_faq = 1
                    AND LENGTH(kb.answer) >= %s
                ORDER BY kb.view DESC, kb.date_mod DESC
            """
            
            if limit:
                query += f" LIMIT {limit}"
            
            cur.execute(query, (min_content_length,))
            faqs = cur.fetchall()
            
            logger.info(f"Buscados {len(faqs)} FAQs do GLPI")
            
            return faqs
    
    def fetch_tickets_for_training(
        self,
        limit: Optional[int] = None,
        status: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            
            if status is None:
                status = [5, 6]
            
            status_placeholders = ",".join(["%s"] * len(status))
            
            query = f"""
                SELECT 
                    t.id,
                    t.name as title,
                    t.content as description,
                    ts.content as solution,
                    t.date as created_at,
                    t.solvedate as solved_at,
                    t.status,
                    t.urgency,
                    t.impact,
                    t.priority,
                    c.name as category
                FROM {self.table_prefix}tickets t
                LEFT JOIN {self.table_prefix}ticketsolutions ts 
                    ON t.id = ts.tickets_id
                LEFT JOIN {self.table_prefix}itilcategories c 
                    ON t.itilcategories_id = c.id
                WHERE t.status IN ({status_placeholders})
                    AND ts.content IS NOT NULL
                    AND LENGTH(ts.content) >= 50
                ORDER BY t.solvedate DESC
            """
            
            if limit:
                query += f" LIMIT {limit}"
            
            cur.execute(query, status)
            tickets = cur.fetchall()
            
            logger.info(f"Buscados {len(tickets)} tickets resolvidos do GLPI")
            
            return tickets
    
    def fetch_categories(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            
            query = f"""
                SELECT 
                    id,
                    name,
                    comment as description,
                    level,
                    itilcategories_id as parent_id
                FROM {self.table_prefix}itilcategories
                ORDER BY level, name
            """
            
            cur.execute(query)
            categories = cur.fetchall()
            
            logger.info(f"Buscadas {len(categories)} categorias do GLPI")
            
            return categories
    
    def get_article_by_id(self, article_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            
            query = f"""
                SELECT 
                    kb.id,
                    kb.name as title,
                    kb.answer as content,
                    kb.date_creation,
                    kb.date_mod,
                    kb.users_id as author_id,
                    kb.view as view_count,
                    kb.is_faq
                FROM {self.table_prefix}knowbaseitems kb
                WHERE kb.id = %s
            """
            
            cur.execute(query, (article_id,))
            article = cur.fetchone()
            
            return article
    
    def increment_article_view(self, article_id: int) -> bool:
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                
                query = f"""
                    UPDATE {self.table_prefix}knowbaseitems
                    SET view = view + 1
                    WHERE id = %s
                """
                
                cur.execute(query, (article_id,))
                conn.commit()
                
                return cur.rowcount > 0
                
        except Exception as e:
            logger.error(f"Erro ao incrementar visualização: {e}")
            return False
    
    def search_articles(
        self,
        search_term: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            
            search_pattern = f"%{search_term}%"
            
            query = f"""
                SELECT 
                    kb.id,
                    kb.name as title,
                    kb.answer as content,
                    kb.date_creation,
                    kb.date_mod,
                    kb.view as view_count
                FROM {self.table_prefix}knowbaseitems kb
                WHERE kb.name LIKE %s
                    OR kb.answer LIKE %s
                ORDER BY kb.view DESC, kb.date_mod DESC
                LIMIT %s
            """
            
            cur.execute(query, (search_pattern, search_pattern, limit))
            articles = cur.fetchall()
            
            logger.info(
                f"Buscados {len(articles)} artigos para termo '{search_term}'"
            )
            
            return articles
    
    def get_statistics(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cur = conn.cursor()
            
            stats = {}
            
            cur.execute(
                f"SELECT COUNT(*) as count FROM {self.table_prefix}knowbaseitems WHERE is_faq=0"
            )
            stats["total_articles"] = cur.fetchone()["count"]
            
            cur.execute(
                f"SELECT COUNT(*) as count FROM {self.table_prefix}knowbaseitems WHERE is_faq=1"
            )
            stats["total_faqs"] = cur.fetchone()["count"]
            
            cur.execute(
                f"SELECT COUNT(*) as count FROM {self.table_prefix}tickets"
            )
            stats["total_tickets"] = cur.fetchone()["count"]
            
            cur.execute(
                f"SELECT COUNT(*) as count FROM {self.table_prefix}tickets WHERE status IN (5, 6)"
            )
            stats["solved_tickets"] = cur.fetchone()["count"]
            
            cur.execute(
                f"SELECT COUNT(*) as count FROM {self.table_prefix}itilcategories"
            )
            stats["total_categories"] = cur.fetchone()["count"]
            
            logger.info(f"Estatísticas GLPI: {stats}")
            
            return stats