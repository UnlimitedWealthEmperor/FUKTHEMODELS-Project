# 🎤 Audio Tags Guide - Eleven V3

Master expressive speech synthesis with audio tags. This guide will help you create more natural, emotional, and engaging audio.

---

## What are Audio Tags?

Audio tags are special markers in `[square brackets]` that control how Eleven V3 delivers speech. They add emotions, vocal sounds, and expressive elements to your audio.

> 💡 **Pro Tip:** Audio tags work best with the Stability slider set to **Creative** or **Natural** mode.

---

## 🎭 Emotions & Delivery

Control the emotional tone of speech.

| Tag | Description | Example |
|-----|-------------|---------|
| `[happy]` | Cheerful, upbeat | `[happy] I just got the best news today!` |
| `[sad]` | Melancholic, downcast | `[sad] I really thought things would be different.` |
| `[excited]` | High energy | `[excited] You won't believe what happened!` |
| `[angry]` | Frustrated, intense | `[angry] This is completely unacceptable!` |
| `[whisper]` | Soft, secretive | `[whisper] Don't tell anyone...` |
| `[sarcastic]` | Ironic, mocking | `[sarcastic] Oh sure, that worked great last time.` |
| `[curious]` | Inquisitive | `[curious] What's behind that door?` |
| `[thoughtful]` | Contemplative | `[thoughtful] I wonder if we made the right choice.` |
| `[surprised]` | Astonished | `[surprised] Wait, you're actually here?` |
| `[annoyed]` | Irritated | `[annoyed] I've already told you three times.` |
| `[cautiously]` | Hesitant | `[cautiously] Are you sure this is safe?` |
| `[cheerfully]` | Bright, positive | `[cheerfully] Good morning everyone!` |
| `[mischievously]` | Playful, scheming | `[mischievously] I have an idea...` |
| `[appalled]` | Shocked, horrified | `[appalled] You did WHAT?` |
| `[elated]` | Overjoyed | `[elated] We actually did it!` |

---

## 🗣️ Non-Verbal Sounds

Add realistic vocal sounds and reactions.

### Laughter
| Tag | Description | Example |
|-----|-------------|---------|
| `[laughs]` | Standard laughter | `[laughs] That's hilarious!` |
| `[chuckles]` | Light, soft laughter | `[chuckles] You always make me smile.` |
| `[giggling]` | Playful laughing | `[giggling] That tickles!` |
| `[laughs harder]` | Intense laughter | `[laughs harder] Stop, I can't breathe!` |
| `[wheezing]` | Breathless laughter | `[wheezing] I can't... stop...` |

### Breathing & Sounds
| Tag | Description | Example |
|-----|-------------|---------|
| `[sighs]` | Emotional exhale | `Well, [sighs] I guess we start over.` |
| `[exhales]` | Releasing breath | `[exhales] Finally, it's done.` |
| `[inhales deeply]` | Deep breath | `[inhales deeply] Okay, let's do this.` |
| `[clears throat]` | Throat clearing | `[clears throat] Ladies and gentlemen...` |
| `[groaning]` | Frustration/pain | `[groaning] Not another meeting...` |
| `[crying]` | Tearful | `[crying] I just miss them so much.` |
| `[snorts]` | Dismissive sound | `[snorts] As if that would work.` |
| `[gulps]` | Nervous swallow | `[gulps] You want me to do what?` |

---

## ⏱️ Pacing & Timing

### Pause Tags
| Tag | Effect | Example |
|-----|--------|---------|
| `[short pause]` | Brief silence | `I think [short pause] we should reconsider.` |
| `[long pause]` | Dramatic pause | `And the winner is [long pause] you!` |

### Punctuation Techniques

Since V3 doesn't support SSML `<break>` tags, use punctuation:

| Technique | Effect | Example |
|-----------|--------|---------|
| `...` (ellipses) | Natural pause, trailing off | `I thought we could... never mind.` |
| `—` (em dash) | Sharp pause, interruption | `Wait — what was that noise?` |
| `CAPS` | Word emphasis | `This is VERY important.` |

---

## ✨ Special & Experimental

> ⚠️ **Warning:** These tags are experimental and may not work consistently with all voices.

| Tag | Description | Example |
|-----|-------------|---------|
| `[strong X accent]` | Apply accent | `[strong French accent] Bonjour, my friend!` |
| `[sings]` | Melodic delivery | `[sings] Happy birthday to you!` |
| `[woo]` | Excited exclamation | `[woo] Let's go!` |

### Sound Effects (Experimental)
| Tag | Example |
|-----|---------|
| `[applause]` | `[applause] Thank you all!` |
| `[gunshot]` | `[gunshot] What was that?!` |
| `[explosion]` | `[explosion] Get down!` |

---

## 🔗 Combining Tags

Layer multiple tags for complex emotions:

### Example 1: Nervous Excitement
```
[excited] Oh my god! [gulps] Is this really happening?
```

### Example 2: Sarcastic Disappointment
```
[sarcastic] Wow, what a surprise. [sighs] I totally didn't see that coming.
```

### Example 3: Emotional Revelation
```
[thoughtful] I've been thinking and... [long pause] [sad] I think we need to talk.
```

### Example 4: Comic Timing
```
[cheerfully] So I walked right up to her and said— [clears throat] [cautiously] Actually, maybe I shouldn't tell this story.
```

---

## 💬 Multi-Speaker Dialogues

### Natural Conversation
```
Speaker A: [excitedly] Sam! Have you tried the new feature?
Speaker B: [curiously] Just got it! The clarity is amazing.
Speaker A: [whispers] Can you keep a secret?
Speaker B: [giggling] Always!
```

### Interruption Pattern
```
Speaker A: [cautiously] Hello, is this seat—
Speaker B: [jumping in] Free? [cheerfully] Yes it is!
```
> 💡 Use em dashes (—) to show cut-off speech

### Trailing Off
```
Speaker A: [indecisive] Hi, can I get uhhh...
Speaker B: [quizzically] The usual?
Speaker A: [elated] Yes! [laughs] I'm so glad you knew!
```
> 💡 Ellipses (...) create natural hesitation

---

## ✅ Best Practices

1. **Match voice to tags**
   - A whispering voice won't suddenly shout well
   - Choose voices that match your intended emotional range

2. **Use Creative stability for expression**
   - Set Stability to "Creative" or "Natural" for best results
   - "Robust" mode reduces tag effectiveness

3. **Don't overuse tags**
   - Too many tags feel unnatural
   - Use them at key emotional moments

4. **Place tags strategically**
   - Tags work best at the beginning of phrases
   - Or right before the affected words

5. **Test and iterate**
   - Different voices respond differently
   - Experiment to find what works

6. **Combine with punctuation**
   - CAPS for emphasis
   - Ellipses for pauses
   - Em dashes for interruptions

---

## 📋 Quick Reference

### Emotions
`[happy]` `[sad]` `[excited]` `[angry]` `[surprised]` `[thoughtful]` `[curious]` `[annoyed]`

### Delivery
`[whisper]` `[sarcastic]` `[cheerfully]` `[cautiously]` `[mischievously]`

### Laughter
`[laughs]` `[chuckles]` `[giggling]` `[laughs harder]` `[wheezing]`

### Breathing
`[sighs]` `[exhales]` `[inhales deeply]` `[clears throat]`

### Reactions
`[groaning]` `[crying]` `[snorts]` `[gulps]`

### Timing
`[short pause]` `[long pause]`

---

*Powered by Eleven V3 - The most expressive speech synthesis model*
