#!/usr/bin/env python3
"""
GPT few-shot 프롬프트로 토픽 기반 논조 데이터셋 생성

Usage:
    python create_stance_dataset_with_gpt.py input.json output.json --api-key YOUR_API_KEY

Input JSON 형식:
[
  {
    "topic": "부동산 규제 완화",
    "title": "정부, 부동산 규제 완화 발표",
    "summary": "정부가 부동산 규제를 완화..."
  }
]

Output JSON 형식:
[
  {
    "topic": "부동산 규제 완화",
    "title": "정부, 부동산 규제 완화 발표",
    "summary": "정부가 부동산 규제를 완화...",
    "stance": "옹호"
  }
]
"""

import json
import sys
import argparse
import time
from typing import List, Dict
import os

try:
    from openai import OpenAI
except ImportError:
    print("❌ OpenAI 패키지가 설치되어 있지 않습니다.")
    print("   pip install openai")
    sys.exit(1)


# System Prompt (논문 기반)
SYSTEM_PROMPT = """입장 분류는 특정 대상에 대한 텍스트의 명시적 또는 묵시적인 의견이나 입장을 결정하는 작업입니다.

토픽과 뉴스 기사(제목 + 요약문)가 제공되며, 당신의 임무는 주어진 토픽에 대한 뉴스 기사의 입장을 옹호, 중립, 비판 중 하나로 분류하는 것입니다.

각 라벨의 판단 기준은 다음과 같습니다:
- 옹호: 토픽에 대해 호의적인 논조, 옹호하는 입장의 인용문을 중심으로 배치하며, 긍정적·낙관적 어조가 지배적인 경우
- 중립: 토픽에 대해 객관적인 논조, 옹호하거나 비판하는 입장의 인용문을 균형 있게 배치하며, 중립적 어조를 사용하는 경우
- 비판: 토픽에 대해 회의적인 논조, 비판하는 입장의 인용문을 중심으로 배치하며, 부정적·비관적 어조가 지배적인 경우

제목과 요약문을 종합적으로 고려하여 토픽에 대한 최종 입장을 결정하세요.
답변은 반드시 '옹호', '중립', '비판' 중 하나만 출력하세요."""


# Few-shot 예시
FEW_SHOT_EXAMPLES = [
    {
        "topic": "부동산 규제 완화",
        "title": "정부, 부동산 대출 규제 완화...주택시장 활성화 기대",
        "summary": "정부가 주택담보대출 규제를 완화하며 침체된 부동산 시장에 활력을 불어넣을 것으로 기대된다. 전문가들은 실수요자들의 주택 구매 부담이 줄어들 것으로 전망했다. 정부 관계자는 이번 조치가 부동산 시장 정상화에 도움이 될 것이라고 밝혔다.",
        "stance": "옹호"
    },
    {
        "topic": "부동산 규제 완화",
        "title": "야당 \"부동산 규제 완화, 집값 폭등 우려\"",
        "summary": "야당은 정부의 부동산 규제 완화 방안이 집값 폭등을 부추길 것이라며 강력히 비판했다. 서민 주거 불안이 가중될 것이라는 우려가 제기됐다. 부동산 전문가들도 투기 수요가 재점화될 가능성을 경고했다.",
        "stance": "비판"
    },
    {
        "topic": "부동산 규제 완화",
        "title": "정부, 부동산 규제 완화 방안 발표",
        "summary": "정부가 14일 부동산 규제 완화 방안을 발표했다. 주요 내용은 대출 규제 완화와 재건축 규제 완화 등이다. 전문가들은 시장 영향을 지켜봐야 한다고 말했다.",
        "stance": "중립"
    }
]


def create_few_shot_messages() -> List[Dict]:
    """Few-shot 예시를 대화 형식으로 생성"""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for example in FEW_SHOT_EXAMPLES:
        user_msg = f"""토픽: {example['topic']}
제목: {example['title']}
요약문: {example['summary']}"""

        messages.append({"role": "user", "content": user_msg})
        messages.append({"role": "assistant", "content": example['stance']})

    return messages


def load_json(file_path: str) -> List[Dict]:
    """JSON 파일 로드"""
    print(f"📂 '{file_path}' 파일을 읽는 중...")

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"✅ {len(data)}개의 항목을 로드했습니다.")
    return data


def analyze_stance_with_gpt(
    client: OpenAI,
    topic: str,
    title: str,
    summary: str,
    model: str = "gpt-5-mini",
    use_few_shot: bool = True
) -> str:
    """
    GPT API를 사용하여 토픽에 대한 논조 분석
    """
    # Few-shot 메시지 생성
    if use_few_shot:
        messages = create_few_shot_messages()
    else:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # 사용자 쿼리 추가
    user_query = f"""토픽: {topic}
제목: {title}
요약문: {summary}"""

    messages.append({"role": "user", "content": user_query})

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.3,
            max_tokens=10
        )

        stance = response.choices[0].message.content.strip()

        # 정규화
        if "옹호" in stance:
            return "옹호"
        elif "비판" in stance:
            return "비판"
        else:
            return "중립"

    except Exception as e:
        print(f"   ❌ GPT API 오류: {str(e)}")
        return None


def create_dataset(
    data: List[Dict],
    api_key: str,
    model: str = "gpt-5-mini",
    use_few_shot: bool = True
) -> List[Dict]:
    """
    GPT로 논조 데이터셋 생성
    """
    client = OpenAI(api_key=api_key)

    total = len(data)
    results = []

    shot_type = "few-shot" if use_few_shot else "zero-shot"
    print(f"\n🤖 GPT {model} ({shot_type})로 논조 분석을 시작합니다...")

    for idx, item in enumerate(data, 1):
        topic = item.get("topic", "정치 토픽")
        title = item.get("title", "")
        summary = item.get("summary", "")

        if not title or not summary:
            print(f"   ⚠️  항목 {idx} 건너뜀 (제목 또는 요약문 없음)")
            continue

        print(f"\n📊 [{idx}/{total}] 분석 중...")
        print(f"   토픽: {topic}")
        print(f"   제목: {title[:50]}...")

        # GPT 분석
        stance = analyze_stance_with_gpt(client, topic, title, summary, model, use_few_shot)

        if stance:
            print(f"   ✅ 논조: {stance}")

            results.append({
                "topic": topic,
                "title": title,
                "summary": summary,
                "stance": stance
            })
        else:
            print(f"   ❌ 분석 실패")

        # API 제한 방지 (RPM/TPM 고려)
        if idx < total:
            time.sleep(1)  # 1초 대기

    success_count = len(results)
    print(f"\n✅ 논조 분석 완료: {success_count}/{total}개 ({success_count/total*100:.1f}%)")

    return results


def save_json(data: List[Dict], output_path: str):
    """JSON 파일로 저장"""
    print(f"\n💾 '{output_path}' 파일로 저장 중...")

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ 저장 완료!")

    # 통계 출력
    if data:
        stance_counts = {}
        for item in data:
            stance = item["stance"]
            stance_counts[stance] = stance_counts.get(stance, 0) + 1

        print(f"\n📊 논조 분포:")
        for stance, count in sorted(stance_counts.items()):
            print(f"   {stance}: {count}개 ({count/len(data)*100:.1f}%)")


def main():
    parser = argparse.ArgumentParser(description="GPT few-shot 프롬프트로 토픽 기반 논조 데이터셋 생성")
    parser.add_argument("input", help="입력 JSON 파일 (topic, title, summary 포함)")
    parser.add_argument("output", help="출력 JSON 파일 (stance 추가됨)")
    parser.add_argument("--api-key", help="OpenAI API 키 (또는 OPENAI_API_KEY 환경변수)")
    parser.add_argument("--model", default="gpt-5-mini", help="GPT 모델 (기본: gpt-5-mini)")
    parser.add_argument("--zero-shot", action="store_true", help="Few-shot 대신 zero-shot 사용")

    args = parser.parse_args()

    # API 키 확인
    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OpenAI API 키가 필요합니다.")
        print("   --api-key 옵션 또는 OPENAI_API_KEY 환경변수 설정")
        sys.exit(1)

    print("=" * 60)
    print("📝 GPT 이슈 기반 논조 데이터셋 생성")
    print("=" * 60)

    # 1. 입력 파일 로드
    data = load_json(args.input)

    # 2. GPT로 논조 분석
    dataset = create_dataset(data, api_key, args.model, use_few_shot=not args.zero_shot)

    # 3. 저장
    save_json(dataset, args.output)

    print("\n" + "=" * 60)
    print("🎉 완료!")
    print("=" * 60)


if __name__ == "__main__":
    main()
