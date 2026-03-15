from typing import Dict, List


def align_packets_to_blueprint(blueprint: List[dict], packets: Dict[int, dict]) -> List[dict]:
    """Stage 6 alignment with sequence fallback."""
    aligned: List[dict] = []
    used_packets = set()

    packet_keys = sorted([int(k) for k in packets.keys() if isinstance(k, int)])
    packet_by_order = [packets[k] for k in packet_keys]
    next_unmatched_idx = 0

    for q in sorted(blueprint, key=lambda x: int(x["question_id"])):
        qid = int(q["question_id"])
        pkt = packets.get(qid)
        aligned_by = "anchor"
        if pkt is None:
            while next_unmatched_idx < len(packet_by_order):
                cand = packet_by_order[next_unmatched_idx]
                next_unmatched_idx += 1
                cand_q = int(cand.get("question_id", -1))
                if cand_q not in used_packets:
                    pkt = cand
                    aligned_by = "sequence_fallback"
                    break
        if pkt:
            used_packets.add(int(pkt.get("question_id", qid)))
        aligned.append(
            {
                "question_id": qid,
                "expected": q,
                "packet": pkt,
                "aligned_by": aligned_by if pkt else "missing",
            }
        )
    return aligned
