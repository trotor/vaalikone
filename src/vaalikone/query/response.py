import os

import litellm

from vaalikone.core.config import get_settings

_settings = get_settings()
if _settings.OPENAI_API_KEY:
    os.environ.setdefault("OPENAI_API_KEY", _settings.OPENAI_API_KEY)


async def generate_response(
    question: str,
    context: list[dict],
    model: str = "gpt-4o",
) -> str:
    """Generate a response using retrieved context and LLM."""

    context_text = "\n\n".join(
        f"[{c.get('party', '?')}] {c.get('title', 'Untitled')}:\n{c.get('snippet') or c.get('chunk_text', '')}"
        for c in context
    )

    messages = [
        {
            "role": "system",
            "content": (
                "Olet suomalaisen politiikan asiantuntija. Vastaa käyttäjän kysymyksiin "
                "annetun kontekstin perusteella. Viittaa aina lähteisiin (puolue ja dokumentti). "
                "Jos kontekstista ei löydy vastausta, kerro se rehellisesti. Vastaa suomeksi."
            ),
        },
        {
            "role": "user",
            "content": f"Konteksti:\n{context_text}\n\nKysymys: {question}",
        },
    ]

    response = await litellm.acompletion(model=model, messages=messages)
    return response.choices[0].message.content
