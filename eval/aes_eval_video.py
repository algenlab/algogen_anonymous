#!/usr/bin/env python3

import openai
import json
import re
import base64
import time
import random
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass
import argparse

import os

SILICONFLOW_KEY = os.getenv("SILICONFLOW_API_KEY", "your-api-key-here")
SILICONFLOW_URL = "https://api.siliconflow.cn/v1"

VISION_MODEL = "zai-org/GLM-4.6V"
TEXT_MODEL = "deepseek-ai/DeepSeek-V3"

client = openai.OpenAI(base_url=SILICONFLOW_URL, api_key=SILICONFLOW_KEY)

# When True, the prompt explicitly asks the model not to penalize Chinese content.
LANGUAGE_NEUTRAL_MODE = True

class TokenStats:
    """Token usage statistics for AES evaluation."""
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset all counters to zero."""
        self.aes_prompt_tokens = 0
        self.aes_completion_tokens = 0
        self.aes_total_tokens = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_tokens = 0
    
    def add_aes_tokens(self, prompt_tokens: int, completion_tokens: int, total_tokens: int):
        """Accumulate token usage for AES evaluation."""
        self.aes_prompt_tokens += prompt_tokens
        self.aes_completion_tokens += completion_tokens
        self.aes_total_tokens += total_tokens
        self._update_total()
    
    def _update_total(self):
        """Recompute total token usage."""
        self.total_prompt_tokens = self.aes_prompt_tokens
        self.total_completion_tokens = self.aes_completion_tokens
        self.total_tokens = self.aes_total_tokens
    
    def get_summary(self) -> dict:
        """Get a summary dictionary of token usage."""
        return {
            'aes': {
                'prompt_tokens': self.aes_prompt_tokens,
                'completion_tokens': self.aes_completion_tokens,
                'total_tokens': self.aes_total_tokens
            },
            'total': {
                'prompt_tokens': self.total_prompt_tokens,
                'completion_tokens': self.total_completion_tokens,
                'total_tokens': self.total_tokens
            }
        }
    
    def print_summary(self):
        """Print a human-readable token usage summary."""
        print("\n" + "="*70)
        print("📊 Token usage statistics")
        print("="*70)
        
        if self.aes_total_tokens > 0:
            print(f"\n[AES aesthetics evaluation]")
            print(f"  Prompt tokens:   {self.aes_prompt_tokens:,}")
            print(f"  Completion tokens: {self.aes_completion_tokens:,}")
            print(f"  Total:           {self.aes_total_tokens:,}")
        
        if self.aes_total_tokens > 0:
            print(f"\n[Total]")
            print(f"  Prompt tokens:   {self.aes_prompt_tokens:,}")
            print(f"  Completion tokens: {self.aes_completion_tokens:,}")
            print(f"  Total tokens:    {self.aes_total_tokens:,}")
            
            # Rough cost estimate for SiliconFlow pricing (adjust as needed).
            cost_estimate = self.total_tokens / 1000 * 0.004
            print(f"  Estimated cost:  ¥{cost_estimate:.4f}")
        
        print("="*70)

# Global token stats instance
token_stats = TokenStats()


# ============================================================================
# Video presets (optional convenience for CLI)
# ============================================================================

VIDEOS = {
    'bubble_sort': {
        'path': 'aigogen_videos/bubble_sort.mp4',
        'name': 'Bubble Sort Algorithm',
    },
    'hamming_distance': {
        'path': 'aigogen_videos/hamming_distance.mp4',
        'name': 'Hamming Distance Computation',
    },
    'quicksort_lomuto': {
        'path': 'aigogen_videos/quicksort_lomuto.mp4',
        'name': 'Quick Sort (Lomuto Partition)',
    },
    'bellman_ford': {
        'path': 'aigogen_videos/bellman_ford.mp4',
        'name': 'Bellman-Ford Shortest Path',
    },
}


# ============================================================================
# API helper
# ============================================================================

def call_api(prompt: str, video_path: str = None, max_retries: int = 3) -> Tuple[str, Dict]:
    """Unified API call helper for SiliconFlow.

    Returns:
        Tuple[str, Dict]: (response text, token usage info)
    """
    for attempt in range(max_retries):
        try:
            if video_path:
                # Video API call (vision model)
                with open(video_path, 'rb') as f:
                    video_base64 = base64.b64encode(f.read()).decode('utf-8')
                
                response = client.chat.completions.create(
                    model=VISION_MODEL,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{video_base64}"}}
                        ]
                    }],
                    max_tokens=4096,
                    temperature=0
                )
            else:
                # Text-only API call (TEXT_MODEL)
                response = client.chat.completions.create(
                    model=TEXT_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2048,
                    temperature=0.3
                )
            
            # Extract token usage information (if provided by API)
            usage = {
                'prompt_tokens': response.usage.prompt_tokens if hasattr(response, 'usage') else 0,
                'completion_tokens': response.usage.completion_tokens if hasattr(response, 'usage') else 0,
                'total_tokens': response.usage.total_tokens if hasattr(response, 'usage') else 0
            }
            
            return response.choices[0].message.content.strip(), usage
            
        except Exception as e:
            if attempt == max_retries - 1:
                raise Exception(f"API call failed: {str(e)}")
            delay = (2 ** attempt) * 0.5 + random.random() * 0.5
            print(f"    ⚠️  Retry ({attempt+1}/{max_retries}) in {delay:.1f}s...")
            time.sleep(delay)


# ============================================================================
# AES evaluation
# ============================================================================

def get_aes_prompt(knowledge_point: str, use_language_neutral: bool = LANGUAGE_NEUTRAL_MODE) -> str:
    """Build the AES evaluation prompt (optionally with language-neutral disclaimer).

    Args:
        knowledge_point: Name of the knowledge point / concept.
        use_language_neutral: Whether to enable language-neutral mode.
    """
    
    # Language-neutral prefix
    language_neutral_prefix = ""
    if use_language_neutral:
        language_neutral_prefix = """
**⚠️ IMPORTANT - LANGUAGE NEUTRALITY REQUIREMENT:**

This is an educational video specifically designed for Chinese-speaking learners and uses Chinese language in its content.

**DO NOT penalize the video for using Chinese text, Chinese pseudocode, or Chinese annotations.**

Your evaluation should focus EXCLUSIVELY on:
- Teaching effectiveness and pedagogical quality
- Visual design quality and aesthetic appeal
- Clarity of knowledge transmission
- Appropriateness of the content structure and presentation

Language choice (Chinese vs. English) is NOT a criterion for evaluation. Do not deduct points or suggest "translating to English" in your feedback.

---

"""
    
    # Knowledge point context
    knowledge_context = ""
    if knowledge_point:
        knowledge_context = f"""
**KNOWLEDGE POINT CONTEXT:**
This educational video is designed to teach: "{knowledge_point}"

Please evaluate the video specifically in relation to how effectively it teaches this particular knowledge point. Consider whether the content, animations, and presentation approach are appropriate and effective for conveying this specific concept.

"""

    return f"""
You are an expert educational content evaluator specializing in instructional videos with synchronized presentations and animations. Please thoroughly analyze the provided educational video across five critical dimensions and provide detailed scoring.

{language_neutral_prefix}{knowledge_context}

**EVALUATION FRAMEWORK:**

**1. Element Layout (20 points)**
Assess the spatial arrangement and organization of visual elements:
- Clarity and readability of text/diagrams in the presentation
- Optimal positioning and sizing of animated content
- Balance between presentation and animation areas
- Appropriate use of whitespace and visual hierarchy
- Consistency in font sizes, colors, and element positioning
- Overall aesthetic appeal and professional appearance

**2. Attractiveness (20 points)**
Evaluate the visual appeal and engagement factors:
- Color scheme harmony and appropriateness for educational content
- Visual design quality and modern aesthetic
- Engaging animation styles and effects
- Creative use of visual metaphors and illustrations
- Ability to capture and maintain learner attention
- Professional presentation quality

**3. Logic Flow (20 points)**
Analyze the pedagogical structure and content progression:
- Clear introduction, development, and conclusion of concepts
- Logical sequence of information presentation
- Smooth transitions between topics and concepts
- Appropriate pacing for learning comprehension
- Coherent connection between presentation content and animations
- Progressive complexity building (scaffolding)

**4. Accuracy and Depth (20 points)**
Evaluate content quality and educational value:
- Factual correctness of all presented information
- Appropriate depth and complexity for the specific knowledge point
- Comprehensive coverage of the key concepts within the knowledge point
- Clarity of explanations and concept definitions relevant to the topic
- Effective use of examples and illustrations that support the knowledge point
- Alignment between video content and the intended learning objective
- Scientific/academic rigor appropriate for the subject matter

**5. Visual Consistency (20 points)**
Assess uniformity and coherence throughout:
- Consistent visual style across all elements
- Uniform color palette and design language
- Coherent animation styles and timing
- Consistent typography and formatting
- Smooth integration between static and animated elements
- Maintaining visual standards throughout the entire video

**SCORING INSTRUCTIONS:**
- Provide a score for each dimension (exact decimal allowed)
- Calculate overall score as sum
- Provide specific feedback for each dimension, considering the knowledge point context
- Evaluate whether the video effectively teaches the specified knowledge point
- Assess if the pedagogical approach is suitable for the subject matter
- Consider if animations and visual elements appropriately support the knowledge point

**RESPONSE FORMAT:**
MUST structure your response in the following JSON format:

{{
"element_layout": {{
    "score": [0-20],
    "feedback": "Detailed analysis of layout quality..."
}},
"attractiveness": {{
    "score": [0-20],
    "feedback": "Assessment of visual appeal..."
}},
"logic_flow": {{
    "score": [0-20],
    "feedback": "Analysis of pedagogical structure..."
}},
"accuracy_depth": {{
    "score": [0-20],
    "feedback": "Evaluation of content quality..."
}},
"visual_consistency": {{
    "score": [0-20],
    "feedback": "Assessment of visual uniformity..."
}},
"overall_score": [0-100],
"summary": "Overall assessment and key recommendations...",
"strengths": ["List of notable strengths"],
"improvements": ["List of suggested improvements"]
}}

Please analyze the video carefully and provide comprehensive, constructive feedback that will help improve future educational content creation.
"""


def _extract_first_json_block(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else ""


def _try_parse_aes_scores_from_text(text: str) -> Dict[str, float]:
    scores = {
        'element_layout': 0.0,
        'attractiveness': 0.0,
        'logic_flow': 0.0,
        'accuracy_depth': 0.0,
        'visual_consistency': 0.0,
    }

    patterns = {
        'element_layout': [
            r'"element_layout"\s*:\s*\{[^\}]*?"score"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
            r'Element\s*Layout\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*20',
        ],
        'attractiveness': [
            r'"attractiveness"\s*:\s*\{[^\}]*?"score"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
            r'Attractiveness\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*20',
        ],
        'logic_flow': [
            r'"logic_flow"\s*:\s*\{[^\}]*?"score"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
            r'Logic\s*Flow\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*20',
        ],
        'accuracy_depth': [
            r'"accuracy_depth"\s*:\s*\{[^\}]*?"score"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
            r'Accuracy\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*20',
        ],
        'visual_consistency': [
            r'"visual_consistency"\s*:\s*\{[^\}]*?"score"\s*:\s*([0-9]+(?:\.[0-9]+)?)',
            r'Consistency\s*[:：]\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*20',
        ],
    }

    for k, pats in patterns.items():
        for pat in pats:
            m = re.search(pat, text, re.DOTALL)
            if m:
                try:
                    scores[k] = float(m.group(1))
                except Exception:
                    scores[k] = 0.0
                break

    return scores


def evaluate_aes(video_path: str, knowledge_point: str) -> Dict:
    """Evaluate the AES score for a single video."""
    print(f"\n🎨 AES aesthetics evaluation")
    print(f"   Video: {Path(video_path).name}")
    print(f"   Knowledge point: {knowledge_point}")
    print(f"   Language-neutral mode: {'✅ Enabled' if LANGUAGE_NEUTRAL_MODE else '❌ Disabled'}")
    
    prompt = get_aes_prompt(knowledge_point)
    
    try:
        print(f"   ⏳ Calling {VISION_MODEL} for analysis...")
        response, usage = call_api(prompt, video_path)
        
        # Record token usage
        token_stats.add_aes_tokens(
            usage['prompt_tokens'],
            usage['completion_tokens'],
            usage['total_tokens']
        )
        
        print(f"   💰 Token usage: {usage['total_tokens']:,} (prompt: {usage['prompt_tokens']:,}, completion: {usage['completion_tokens']:,})")
        
        parse_error = None
        repaired_json = None
        data = None

        raw_json = _extract_first_json_block(response)
        if raw_json:
            try:
                data = json.loads(raw_json)
            except Exception as e:
                parse_error = str(e)
        else:
            parse_error = "No JSON-formatted response found"

        if data is None:
            try:
                repair_prompt = (
                    "You are a strict JSON formatter. "
                    "Given the following text that should contain a JSON object, "
                    "output ONLY a valid JSON object that matches this schema exactly: "
                    "{element_layout:{score:number,feedback:string},attractiveness:{score:number,feedback:string}," 
                    "logic_flow:{score:number,feedback:string},accuracy_depth:{score:number,feedback:string}," 
                    "visual_consistency:{score:number,feedback:string},overall_score:number,summary:string,strengths:[string],improvements:[string]}. "
                    "Do not add any extra keys. Do not wrap in markdown.\n\n" 
                    "TEXT:\n" + response
                )
                repaired_text, _ = call_api(repair_prompt, video_path=None, max_retries=2)
                repaired_json = _extract_first_json_block(repaired_text) or repaired_text.strip()
                data = json.loads(repaired_json)
            except Exception as e:
                if not parse_error:
                    parse_error = str(e)

        if data is not None:
            scores = {
                'element_layout': float(data.get('element_layout', {}).get('score', 0) or 0),
                'attractiveness': float(data.get('attractiveness', {}).get('score', 0) or 0),
                'logic_flow': float(data.get('logic_flow', {}).get('score', 0) or 0),
                'accuracy_depth': float(data.get('accuracy_depth', {}).get('score', 0) or 0),
                'visual_consistency': float(data.get('visual_consistency', {}).get('score', 0) or 0)
            }
        else:
            scores = _try_parse_aes_scores_from_text(response)
            if repaired_json:
                repaired_scores = _try_parse_aes_scores_from_text(repaired_json)
                for k, v in repaired_scores.items():
                    if scores.get(k, 0.0) == 0.0 and v != 0.0:
                        scores[k] = v

        overall = sum(scores.values())

        if parse_error:
            print(f"   ⚠️ JSON parse error; attempted to recover scores from text: {parse_error}")

        print(f"\n   📊 Scores:")
        print(f"      Total: {overall:.1f}/100")

        result = {
            'knowledge_point': knowledge_point,
            'scores': {**scores, 'overall': overall},
            'raw_response': response,
            'token_usage': usage
        }
        if parse_error:
            result['parse_error'] = parse_error
        if repaired_json:
            result['repaired_json'] = repaired_json

        return result
            
    except Exception as e:
        print(f"\n   ❌ AES evaluation failed: {e}")
        return None


# ============================================================================
# CLI entry (AES-only)
# ============================================================================


def main():
    parser = argparse.ArgumentParser(description='AES aesthetics evaluation for a single video')
    parser.add_argument('video', choices=['bubble_sort', 'hamming_distance', 'quicksort_lomuto', 'bellman_ford'],
                       help='Preset video key to evaluate')
    parser.add_argument('--video-path', type=str,
                       help='Path to an arbitrary video file; overrides the preset path from --video')
    parser.add_argument('--knowledge-point', type=str,
                       help='Override knowledge point name; default depends on preset video or file name')

    args = parser.parse_args()

    base_dir = Path(__file__).parent

    if args.video_path:
        # Custom video path; do not rely on VIDEOS mapping for path.
        video_path = Path(args.video_path)
        if not video_path.is_absolute():
            video_path = (base_dir / video_path).resolve()
        # Derive knowledge point from CLI or file name.
        knowledge_point = args.knowledge_point or video_path.stem
        report_key = video_path.stem
    else:
        video_config = VIDEOS[args.video]
        video_path = (base_dir / video_config['path']).resolve()
        knowledge_point = args.knowledge_point or video_config['name']
        report_key = args.video

    print("="*70)
    print(f"🎯 Evaluating video: {report_key}")
    print("="*70)
    print(f"Video path: {video_path}")
    print(f"Knowledge point: {knowledge_point}")
    print(f"API: {SILICONFLOW_URL}")
    print(f"Vision model: {VISION_MODEL}")
    print(f"Text model: {TEXT_MODEL}")
    print(f"Language-neutral mode: {'✅ Enabled (no penalty for Chinese)' if LANGUAGE_NEUTRAL_MODE else '❌ Disabled (original standard)'}")
    print("="*70)

    # Check video file
    if not video_path.exists():
        print(f"\n❌ Video file does not exist: {video_path}")
        return

    size_mb = video_path.stat().st_size / 1024 / 1024
    print(f"✅ Video file size: {size_mb:.1f} MB")

    # Create report directory
    reports_dir = base_dir / 'reports' / report_key
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Suffix depends on whether language-neutral mode is enabled
    suffix = "_neutral" if LANGUAGE_NEUTRAL_MODE else ""

    # Reset token stats
    token_stats.reset()

    # Run AES-only evaluation
    print("\n" + "="*70)
    print("[1/1] AES aesthetics evaluation")
    print("="*70)
    aes_result = evaluate_aes(video_path, knowledge_point)

    if aes_result:
        aes_result['evaluation_config'] = {
            'language_neutral_mode': LANGUAGE_NEUTRAL_MODE,
            'vision_model': VISION_MODEL
        }
        aes_result['token_usage_summary'] = token_stats.get_summary()
        json_path = reports_dir / f'aes_result{suffix}.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(aes_result, f, ensure_ascii=False, indent=2)
        print(f"\n📁 Result saved: {json_path}")

    # Print token usage summary
    token_stats.print_summary()

    print("\n✅ AES evaluation finished!")


if __name__ == '__main__':
    main()

