import google.genai as genai
from config import GEMINI_API_KEY
import asyncio
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
import re

# Configurar o cliente do Gemini (SDK novo)
client = genai.Client(api_key=GEMINI_API_KEY)

# Modelo estável confirmado para esta conta específica
MODEL_ID = 'gemini-2.5-flash'

# Semaforo para evitar excesso de requisições simultâneas e garantir estabilidade
gemini_semaphore = asyncio.Semaphore(1)

def log_retry(retry_state):
    print(f"🔄 Tentativa {retry_state.attempt_number} de chamada ao Gemini falhou. Tentando novamente em {retry_state.next_action.sleep}s...")

PROMPT_SISTEMA = """
Você é a especialista em ofertas literárias do canal 'LITERALMENTE PROMO'.
Sua tarefa é criar posts ENCANTADORES, DIRETOS e IRRESISTÍVEIS para leitores apaixonados!

REGRAS DE OURO:
1. SEJA RESUMIDA E DIRETA AO PONTO. O texto deve ser de fácil e rápida leitura.
2. USE UM TOM EMPOLGANTE E ACONCHEGANTE! Use frases curtas que cativem leitores como "<b>LEITURA OBRIGATÓRIA!</b>", "<b>PREÇO IMPERDÍVEL PARA A SUA ESTANTE!</b>".
3. USE APENAS HTML PARA FORMATAR: <b>negrito</b> e <code>código</code>. NUNCA use markdown como **negrito** ou `código`. Se usar markdown, o sistema falhará.
4. PREÇOS: NUNCA INVENTE informações de preço. Mostre apenas o preço atual da oferta.
5. USE EMOJIS literários variados (📚, 📖, 🔖, ✨, ☕, 🦉) para tornar o texto visualmente rico.
6. NUNCA mencione outros canais, grupos ou concorrentes. REMOVA qualquer link de terceiros.
7. CUPOM COPIÁVEL E AZUL: O cupom DEVE obrigatoriamente aparecer como um link azul e ser copiável ao toque. Para isso, use a formatação combinada de link e código: `<a href="https://t.me/promosliterais"><code>CÓDIGO_AQUI</code></a>`. Exemplo correto: `Use o Cupom: <a href="https://t.me/promosliterais"><code>LIVRO10</code></a>`. NUNCA use `<code>` na palavra "Cupom", aplique apenas no código em si.
8. NUNCA use a tag <br> ou <p>. Use quebras de linha reais.
9. PRESERVE OS LINKS INLINE: O texto original conterá marcações como [LINK_0], [LINK_1], etc. Você DEVE manter essas marcações EXATAMENTE onde elas estavam. Se estiver criando um texto DO ZERO para um novo post, você DEVE terminar o corpo do texto com a marcação [LINK_0] para que o botão de compra seja inserido.
10. NUNCA termine o texto com emojis de carrinho ou setas de link se não houver um [LINK_X] logo depois.

Retorne APENAS o HTML final. Use apenas as tags <b> e <code>.
"""

def limpar_emojis_finais(texto: str) -> str:
    """
    Remove emojis de call-to-action (carrinho, setas) que o Gemini teima em colocar no final
    para que não fiquem duplicados ou 'soltos' antes do link real.
    """
    # Remove espaços e quebras de linha no fim
    texto = texto.rstrip()
    # Regex para remover especificamente 🛒, 🖱️, ⬇️, 👉, 🔗 no final do texto
    texto = re.sub(r'[🛒🖱️⬇️👉🔗\s]+$', '', texto)
    return texto.strip()

@retry(
    wait=wait_exponential(multiplier=1, min=5, max=20),
    stop=stop_after_attempt(3),
    before_sleep=log_retry,
    reraise=True
)
async def _call_gemini_api(prompt: str) -> str:
    # Esta função interna permite o retry funcionar de verdade
    async with gemini_semaphore:
        response = await client.aio.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        # Pequeno intervalo para segurança
        await asyncio.sleep(1)
        return response.text.strip()

async def extrair_nome_produto(texto: str) -> str:
    """Extrai apenas o nome curto e principal do produto de um texto promocional usando o Gemini."""
    prompt = f"""
Extraia APENAS o nome do produto principal deste texto promocional.
Regras:
1. Retorne apenas o NOME do produto (ex: Smartphone Samsung Galaxy S25, Caixa de Som Tribit StormBox).
2. NÃO inclua adjetivos de promoção (ex: 'menor preço', 'promoção', 'barato').
3. NÃO inclua o preço.
4. Seja o mais breve e preciso possível (idealmente entre 2 a 6 palavras).
5. Se não houver produto claro, retorne exatamente o texto "Oferta Desconhecida".

Texto:
{texto}
"""
    try:
        resultado = await _call_gemini_api(prompt)
        nome = resultado.strip()
        # Fallback de segurança caso a IA ainda retorne um texto muito longo
        if len(nome.split()) > 15:
            nome = " ".join(nome.split()[:7])
        return nome
    except Exception as e:
        print(f"⚠️ Erro ao extrair nome do produto com Gemini: {e}")
        return ""

@retry(
    wait=wait_exponential(multiplier=1, min=5, max=20),
    stop=stop_after_attempt(3),
    before_sleep=log_retry,
    reraise=True
)
async def _call_gemini_api(prompt: str) -> str:
    # Esta função interna permite o retry funcionar de verdade
    async with gemini_semaphore:
        print(f"📡 Chamando Gemini ({MODEL_ID})...")
        response = await client.aio.models.generate_content(
            model=MODEL_ID,
            contents=prompt
        )
        # Pequeno intervalo para segurança
        await asyncio.sleep(1)
        res_text = response.text.strip()
        print(f"✨ Gemini respondeu ({len(res_text)} caracteres)")
        return res_text

async def reescrever_promocao(texto_original: str) -> str:
    """
    Envia o texto original para o Gemini de forma assíncrona e retorna a versão reescrita.
    """
    try:
        prompt = f"{PROMPT_SISTEMA}\n\nTEXTO ORIGINAL:\n{texto_original}\n\nTEXTO REESCRITO:"
        reescrito = await _call_gemini_api(prompt)
        return limpar_emojis_finais(reescrito)
    except Exception as e:
        print(f"❌ Falha definitiva ao reescrever com Gemini após retries: {e}")
        return texto_original

async def gerar_promocao_por_link(titulo: str, link: str, preco: str, cupom: str, observacao: str = "") -> str:
    """
    Gera um texto de promoção do zero baseado nos dados scraped da URL e inputs manuais.
    """
    if not titulo:
        titulo = "Oferta Imperdível"
        
    cupom_str = f"Tem Cupom: <code>{cupom}</code>" if cupom and cupom.lower() not in ['não', 'nao', 'nenhum', '-'] else "Sem cupom específico."
    obs_str = f"- Observação/Destaque: {observacao}" if observacao and observacao.strip() else ""
    
    prompt = f"""
{PROMPT_SISTEMA}

INSTRUÇÃO ESPECIAL: Você não está reescrevendo um texto, está CRIANDO UM DO ZERO.
DADOS DO PRODUTO:
- Produto/Título Original: {titulo}
- Preço da Promoção: R$ {preco}
- {cupom_str}
{obs_str}

REGRAS ADICIONAIS:
1. Comece o post de forma impactante.
2. IMPORTANTE: Termine o seu texto obrigatoriamente com a marcação [LINK_0] em uma nova linha para que o botão de compra seja inserido.
3. Use tags <b> para o nome do livro e para o preço.
4. Nunca use Markdown (**).

TEXTO GERADO:
"""
    try:
        gerado = await _call_gemini_api(prompt)
        return limpar_emojis_finais(gerado)
    except Exception as e:
        print(f"❌ Falha definitiva ao gerar texto com Gemini: {e}")
        obs_final = f"\n💡 {observacao}" if observacao else ""
        return f"🔥 <b>{titulo}</b>\n\n✅ Por Apenas <b>R$ {preco}</b>\n{cupom_str}{obs_final}\n\n[LINK_0]"
