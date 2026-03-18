import asyncio
from app.services.answer_sheet_pipeline import pdf_to_clean_images, run_answer_packet_pipeline
from app.core.logging_config import logger

async def extract_answers_from_pdf(pdf_bytes: bytes, questions: list):
    """
    Centralized extraction logic: PDF -> Images -> Answer Packets.
    """
    # Extract images from PDF bytes (CPU intensive)
    images = await asyncio.to_thread(pdf_to_clean_images, pdf_bytes)
    
    # Run alignment and extraction pipeline
    packets = await run_answer_packet_pipeline(
        answer_images=images,
        questions=questions
    )
    # log packet summary for debugging
    try:
        total = len(packets) if isinstance(packets, dict) else 0
        logger.info(f"extract_answers_from_pdf: extracted {total} packets")
        if isinstance(packets, dict):
            for k,v in packets.items():
                if isinstance(v, dict) and v.get("combined_text") is not None:
                    logger.debug(f"packet {k} text length={len(v.get('combined_text',''))}")
    except Exception:
        pass
    
    return packets
