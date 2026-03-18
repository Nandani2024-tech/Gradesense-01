import asyncio
from app.services.answer_sheet_pipeline import pdf_to_clean_images, run_answer_packet_pipeline
from app.core.logging_config import logger
from app.adapters.interfaces import AbstractOCRService

async def extract_answers_from_pdf(pdf_bytes: bytes, questions: list, ocr_service: AbstractOCRService):
    """
    Centralized extraction logic: PDF -> Images -> Answer Packets.
    """
    # Extract images from PDF bytes (CPU intensive)
    images = await asyncio.to_thread(pdf_to_clean_images, pdf_bytes)
    
    # Run alignment and extraction pipeline
    packets = await asyncio.to_thread(
        run_answer_packet_pipeline,
        answer_images=images,
        questions=questions,
        ocr_service=ocr_service
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
