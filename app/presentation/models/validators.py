import re
from typing import Any
from pydantic import validator, Field
from datetime import datetime

class AdvancedValidators:
    """Validadores reutilizáveis para Pydantic"""
    
    @staticmethod
    def validate_email(email: str) -> str:
        """Validação avançada de email"""
        email = email.lower().strip()
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        
        if not re.match(pattern, email):
            raise ValueError("Email inválido")
        
        # Verifica domínios bloqueados (exemplo)
        blocked_domains = ['tempmail.com', '10minutemail.com']
        domain = email.split('@')[1]
        if domain in blocked_domains:
            raise ValueError("Domínio de email não permitido")
        
        return email
    
    @staticmethod
    def validate_password(password: str) -> str:
        """Validação de senha forte"""
        if len(password) < 8:
            raise ValueError("Senha deve ter pelo menos 8 caracteres")
        
        if not re.search(r'[A-Z]', password):
            raise ValueError("Senha deve conter pelo menos uma letra maiúscula")
        
        if not re.search(r'[a-z]', password):
            raise ValueError("Senha deve conter pelo menos uma letra minúscula")
        
        if not re.search(r'[0-9]', password):
            raise ValueError("Senha deve conter pelo menos um número")
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            raise ValueError("Senha deve conter pelo menos um caractere especial")
        
        return password
    
    @staticmethod
    def validate_phone(phone: str) -> str:
        """Validação de telefone brasileiro"""
        # Remove caracteres não numéricos
        phone = re.sub(r'\D', '', phone)
        
        # Verifica formato brasileiro
        if len(phone) == 11:
            # Celular com DDD
            if not re.match(r'^[1-9]{2}9[0-9]{8}$', phone):
                raise ValueError("Número de celular inválido")
        elif len(phone) == 10:
            # Fixo com DDD
            if not re.match(r'^[1-9]{2}[2-5][0-9]{7}$', phone):
                raise ValueError("Número de telefone fixo inválido")
        else:
            raise ValueError("Número de telefone deve ter 10 ou 11 dígitos")
        
        return phone
    
    @staticmethod
    def validate_cpf(cpf: str) -> str:
        """Validação de CPF brasileiro"""
        # Remove caracteres não numéricos
        cpf = re.sub(r'\D', '', cpf)
        
        if len(cpf) != 11:
            raise ValueError("CPF deve ter 11 dígitos")
        
        # Verifica se todos os dígitos são iguais
        if len(set(cpf)) == 1:
            raise ValueError("CPF inválido")
        
        # Validação dos dígitos verificadores
        def calculate_digit(cpf_partial):
            s = sum(int(cpf_partial[i]) * (len(cpf_partial) + 1 - i) 
                   for i in range(len(cpf_partial)))
            remainder = s % 11
            return '0' if remainder < 2 else str(11 - remainder)
        
        if cpf[9] != calculate_digit(cpf[:9]):
            raise ValueError("CPF inválido")
        
        if cpf[10] != calculate_digit(cpf[:10]):
            raise ValueError("CPF inválido")
        
        return cpf
    
    @staticmethod
    def validate_cnpj(cnpj: str) -> str:
        """Validação de CNPJ brasileiro"""
        # Remove caracteres não numéricos
        cnpj = re.sub(r'\D', '', cnpj)
        
        if len(cnpj) != 14:
            raise ValueError("CNPJ deve ter 14 dígitos")
        
        # Verifica se todos os dígitos são iguais
        if len(set(cnpj)) == 1:
            raise ValueError("CNPJ inválido")
        
        # Validação dos dígitos verificadores
        def calculate_digit(cnpj_partial, weights):
            s = sum(int(cnpj_partial[i]) * weights[i] 
                   for i in range(len(cnpj_partial)))
            remainder = s % 11
            return '0' if remainder < 2 else str(11 - remainder)
        
        weights1 = [5,4,3,2,9,8,7,6,5,4,3,2]
        weights2 = [6,5,4,3,2,9,8,7,6,5,4,3,2]
        
        if cnpj[12] != calculate_digit(cnpj[:12], weights1):
            raise ValueError("CNPJ inválido")
        
        if cnpj[13] != calculate_digit(cnpj[:13], weights2):
            raise ValueError("CNPJ inválido")
        
        return cnpj