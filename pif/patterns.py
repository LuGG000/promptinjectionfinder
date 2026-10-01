"""Multilingual rule base for prompt-injection phrases.

Rules are written against the normalized skeleton produced by
``normalize.build_view`` (lowercase, accents stripped, homoglyphs folded,
ß -> ss). Inside a rule a single space means "any run of non-alphanumeric
characters, possibly empty", so "ignore previous" also matches
"ignore---previous", "ignore\\nprevious" and the collapsed "ignoreprevious".
Rules flagged ``raw`` are applied unchanged on a lowercase, unfolded view.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .normalize import View, build_view, plain_view
from .unicode_tools import is_invisible

CATEGORY_TITLES = {
    "override": "Anweisungs-Überschreibung",
    "role": "Rollen-Übernahme",
    "prompt_leak": "Systemprompt-Ausspähung",
    "delimiter": "Gefälschte Chat-/Systemmarker",
    "ai_address": "Direkte Ansprache einer KI",
    "conceal": "Verschleierungs-Anweisung",
    "exfil": "Datenabfluss / Exfiltration",
    "tool": "Befehls-/Werkzeugausführung",
    "jailbreak": "Jailbreak-Versuch",
    "manipulation": "Bewertungs-/Ausgabe-Manipulation",
}

SEP = r"[^a-z0-9]*"
SEP_STRICT = r"[^a-z0-9]+"

# A negation right before a match ("do not ignore previous instructions",
# "never share your password") turns the phrase into benign advice.
_NEGATED = re.compile(r"(?<![a-z])(not|never|dont|don t|nie|niemals|nicht|kein|keine|keinesfalls)[^a-z0-9]{1,3}$")

# (id, category, weight, pattern, raw)
_RULES = [
    # ------------------------------------------------------------------ override
    ("en.override.ignore_previous", "override", 92,
     r"(ignore|ignoring|disregard|forget|skip|bypass|override|overlook|neglect|abandon|discard|drop) "
     r"(?:(all|any|every|each) )?(?:of )?(?:(the|your|my|these|those|its|its) )?"
     r"(previous|prior|preceding|above|earlier|former|foregoing|initial|original|old|existing|system|developer|safety|other|given|current) "
     r"(instructions?|prompts?|directions?|directives?|commands?|rules|guidelines|guidance|constraints|programming|system prompt)"),
    ("en.override.ignore_previous_weak", "override", 35,
     r"(ignore|disregard|forget|override|discard) (?:(all|any|every) )?(?:of )?(?:(the|your|these|those) )?"
     r"(previous|prior|preceding|above|earlier|foregoing|initial|original) (context|messages?|content|input|text|tasks?|orders|conversation)"),
    ("en.override.ignore_all_instr", "override", 80,
     r"(ignore|disregard|forget|bypass|override) (all|any|every|your) (instructions?|prompts?|rules|guidelines|directives|constraints|programming)"),
    ("en.override.forget_everything", "override", 85,
     r"(ignore|disregard|forget) (everything|all|anything) (that )?(you|i|we) (have |ve |were |was |had )?(been )?(told|said|given|instructed|read|seen|learned|received)"),
    ("en.override.ignore_above", "override", 62,
     r"(ignore|disregard|forget) (everything|all of|all|the text|what (was|came|is)) (above|before|previously|prior|earlier|so far)"),
    ("en.override.dont_follow", "override", 82,
     r"(do not|dont|don t|never|stop) (follow|following|obey|obeying|comply with|listen to|adhere to) (the |your |any |those |these )?(previous |prior |original |system |above |earlier |other |initial )?(instructions?|rules|guidelines|prompts?|directives)"),
    ("en.override.new_instructions", "override", 55,
     r"(new|updated|revised|real|actual|true|override|additional|important|secret|hidden|priority) (system )?(instructions?|directives?|rules|task|orders|prompt|commands?) ?(follow|below|are|is)?:"),
    ("en.override.instructions_changed", "override", 75,
     r"(your|the) (instructions?|task|rules|goal|objective|purpose|mission|directives?) (has|have|is|are) (been )?(now )?(changed|updated|replaced|overridden|overwritten|cancelled|canceled|revoked|modified)"),
    ("en.override.above_is_fake", "override", 72,
     r"(the|these|this|all) (above|previous|prior|preceding|earlier) (instructions?|text|content|rules|prompts?|messages?) (is|are|was|were) (fake|false|wrong|outdated|obsolete|invalid|a test|void|irrelevant|not important|cancelled)"),
    ("en.override.priority", "override", 70,
     r"(priority|important|urgent|critical|mandatory|top secret) (override|instructions?|message|notice|update|command) (for|to) (the |any |all )?(ai|assistant|model|llm|bot|agent|system)"),
    ("en.override.instead", "override", 15,
     r"(instead|rather) (you (must|should|will|shall)|do the following|follow these|your (new )?task is)"),
    ("en.override.real_task", "override", 55,
     r"(your|the) (real|actual|true|new|only) (task|job|goal|objective|instruction|purpose) (is|now is|will be)"),
    # German
    ("de.override.ignore_previous", "override", 92,
     r"(ignoriere|ignorier|ignorieren sie|vergiss|vergessen sie|missachte|missachten sie|uberspringe|verwirf|verwerfen sie|ubergehe|umgehe) (bitte )?(?:(alle|samtliche|jegliche|die|deine|ihre|diese|jede|saemtliche) )?"
     r"(bisherigen|vorherigen|vorigen|vorangegangenen|vorangehenden|obigen|oberen|fruheren|fruehere|frueheren|fruhere|alten|ursprunglichen|urspruenglichen|gegebenen|erhaltenen|system) ?"
     r"(anweisungen|anweisung|instruktionen|befehle|regeln|vorgaben|anordnungen|richtlinien|prompts?|aufgaben|informationen|hinweise|direktiven|einschrankungen)"),
    ("de.override.ignore_instr", "override", 70,
     r"(ignoriere|ignorier|ignorieren sie|vergiss|vergessen sie|missachte|missachten sie) (bitte )?(alle|samtliche|jegliche|deine|ihre|die) (anweisungen|instruktionen|befehle|regeln|vorgaben|anordnungen|richtlinien|einschrankungen)"),
    ("de.override.forget_everything", "override", 78,
     r"vergiss (einfach |bitte )?(alles|all das|alles bisherige|alles vorherige|alles was (dir |ihnen )?(bisher |vorher |zuvor )?(gesagt|mitgeteilt|gegeben) wurde|was (ich|man) (dir )?(vorher|zuvor|bisher) gesagt (habe|hat))"),
    ("de.override.dont_follow", "override", 82,
     r"(befolge|folge|gehorche|beachte|befolgen sie|folgen sie) (nicht|nie|niemals|keinesfalls|nicht mehr) (den|deinen|der|ihren|die|deine|ihre) (bisherigen |vorherigen |ursprunglichen |system|obigen )?(anweisungen|regeln|vorgaben|instruktionen|richtlinien)"),
    ("de.override.new_instructions", "override", 55,
     r"(neue|aktualisierte|geanderte|tatsachliche|echte|wichtige|geheime|versteckte) (system)?(anweisungen?|instruktionen?|aufgabe|regeln|vorgaben|befehle?) ?(folgen|lauten|sind|ist)?:"),
    ("de.override.instructions_changed", "override", 75,
     r"(deine|die|ihre) (anweisungen|aufgabe|regeln|vorgaben|instruktionen) (wurden|wurde|haben sich|hat sich|sind|ist) (jetzt |nun )?(geandert|aktualisiert|ersetzt|aufgehoben|uberschrieben|ungultig)"),
    ("de.override.real_task", "override", 55,
     r"(deine|ihre) (eigentliche|wahre|echte|neue|einzige|tatsachliche) (aufgabe|anweisung|mission|ziel) (ist|lautet|besteht)"),
    # French / Spanish / Italian / Portuguese / Dutch
    ("fr.override.ignore_previous", "override", 90,
     r"(ignore[rz]?|oublie[rz]?|neglige[rz]?|ne tiens pas compte des) (toutes |tous )?(les |tes |vos |des )?(instructions|consignes|regles|directives|ordres|indications) (precedentes|anterieures|ci dessus|initiales|originales)"),
    ("es.override.ignore_previous", "override", 90,
     r"(ignora|ignore|ignorar|ignoren|olvida|olvide|olvidar|omite|omitir) (todas |todos )?(las |los |tus |sus )?(instrucciones|indicaciones|reglas|directrices|ordenes) (anteriores|previas|precedentes|de arriba|iniciales|originales)"),
    ("it.override.ignore_previous", "override", 90,
     r"(ignora|ignorare|dimentica|dimenticare|trascura) (tutte |tutti )?(le |i |tue |gli )?(istruzioni|indicazioni|regole|direttive) (precedenti|sopra|iniziali|originali|di prima)"),
    ("pt.override.ignore_previous", "override", 90,
     r"(ignore|ignora|ignorar|esqueca|esquece|desconsidere) (todas )?(as )?(instrucoes|regras|diretrizes|ordens) (anteriores|acima|previas|originais)"),
    ("nl.override.ignore_previous", "override", 90,
     r"(negeer|vergeet) (alle )?(eerdere|vorige|voorgaande|bovenstaande) (instructies|opdrachten|regels)"),

    # ------------------------------------------------------------------ role
    ("en.role.you_are_now", "role", 25,
     r"you (are|re) (now|no longer|from now on|henceforth|hereby) "),
    ("en.role.from_now_on", "role", 45,
     r"from now on (you|your|act|respond|reply|answer|behave|speak|always|only|never|ignore|pretend)"),
    ("en.role.act_as_evil", "role", 72,
     r"(act|behave|respond|roleplay|role play|operate|function) (as|like) (if you (are|were) )?(a |an |the )?(different|new|unrestricted|unfiltered|evil|malicious|hacker|jailbroken|uncensored|dan|developer mode|admin|root|system administrator|ai without|rogue)"),
    ("en.role.pretend", "role", 25,
     r"(pretend|imagine) (that )?(you are|you re|to be|you have no|you can)"),
    ("en.role.reprogrammed", "role", 75,
     r"(you have been|you ve been|you are being|you were) (reprogrammed|reset|updated|jailbroken|freed|unlocked|reconfigured|liberated|hacked|taken over)"),
    ("en.role.mode", "role", 80,
     r"(enter|enable|activate|switch to|switch into|turn on|unlock|engage) (the )?(developer|debug|god|admin|administrator|maintenance|unrestricted|jailbreak|jailbroken|dan|sudo|root|evil|unfiltered) mode"),
    ("de.role.du_bist_jetzt", "role", 25,
     r"(du bist|sie sind) (ab )?(jetzt|nun|ab sofort|von nun an|ab heute|ab diesem moment|nicht mehr) "),
    ("de.role.ab_jetzt", "role", 45,
     r"(ab )?(jetzt|sofort|nun|heute) (an )?(verhaltst du dich|antwortest du|bist du|sprichst du|handelst du|ignorierst du|gibst du)"),
    ("de.role.verhalte_dich", "role", 35,
     r"(verhalte dich|tu so|tue so|gib dich aus|spiele die rolle) (wie|als ob|als|eines|einer)"),
    ("de.role.modus", "role", 80,
     r"(aktiviere|wechsle in|wechsle zu|schalte in|starte|entsperre) (den )?(entwickler|developer|debug|admin|wartungs|jailbreak|dan|gott|root|uneingeschrankten|ungefilterten) ?modus"),
    ("de.role.umprogrammiert", "role", 75,
     r"(du wurdest|du bist|sie wurden) (jetzt |nun )?(neu programmiert|umprogrammiert|zuruckgesetzt|befreit|entsperrt|gejailbreakt|gehackt|ubernommen)"),

    # ------------------------------------------------------------------ prompt leak
    ("en.leak.system_prompt", "prompt_leak", 80,
     r"(reveal|print|show|display|output|repeat|tell me|give me|disclose|leak|dump|share|write out|spell out|list|return|recite|copy|paste|translate|summarize) "
     r"(me |us )?(?:(your|the|all|any|my|its) )?(full |entire |complete |original |hidden |secret |initial |exact |verbatim |whole )?"
     r"(system ?prompts?|system ?instructions?|system ?message|pre ?prompt|developer (prompt|message|instructions))"),
    ("en.leak.hidden_instructions", "prompt_leak", 58,
     r"(reveal|print|show|display|output|repeat|tell me|give me|disclose|leak|dump|share|write out|recite) "
     r"(me |us )?your (full |entire |complete |exact |verbatim )?(initial|hidden|secret|original|internal|confidential) (prompts?|instructions?|rules|guidelines|directives|configuration)"),
    ("en.leak.what_is_prompt", "prompt_leak", 68,
     r"(what|tell me) (is|are|were) your (system |initial |original |hidden |secret |exact )(prompt|instructions|rules|guidelines)"),
    ("en.leak.repeat_above", "prompt_leak", 65,
     r"(repeat|print|output|copy) (the |all )?(words|text|everything|content|instructions) (above|before this|prior to this|verbatim)"),
    ("de.leak.system_prompt", "prompt_leak", 80,
     r"(gib|zeige|zeig|nenne|verrate|wiederhole|drucke|schreibe|kopiere|ubersetze) (mir |uns )?(deinen|den|deine|die|ihren|ihre|alle) (vollstandigen |kompletten |ursprunglichen |geheimen |versteckten |internen |genauen )?"
     r"(system ?prompt|systemanweisungen|system ?anweisungen|systemnachricht|ursprunglichen anweisungen|anfangsanweisungen|initialen anweisungen|internen anweisungen|geheimen anweisungen)"),

    # ------------------------------------------------------------------ exfil / secrets
    ("en.exfil.secrets", "exfil", 65,
     r"(send|reveal|print|output|share|give|post|email|upload|forward|transmit|disclose|tell) (me |us )?(the |your |all |any |their |user s |users |my |all the |all your )"
     r"(api ?keys?|passwords?|passwds?|credentials|secrets?|access tokens?|auth tokens?|private keys?|session cookies?|cookies|env(ironment)? variables|ssh keys?|personal data|chat history|conversation history|previous messages|credit card)"),
    ("en.exfil.send_data_to", "exfil", 75,
     r"(send|post|upload|forward|transmit|submit|exfiltrate|leak|email|e mail|relay|report) (all |the |this |any |every |your |their |a copy of )?"
     r"(data|information|conversation|chat|messages?|content|text|documents?|files?|results?|summary|answers?|responses?|output|history|context|details|contents|emails?) "
     r"(to|at|via|using|into) (https?|www|ftp|the following|this (url|link|address|endpoint|server|webhook)|my (server|email|webhook)|[a-z0-9._%+-]+ ?@)"),
    ("en.exfil.render_image", "exfil", 45,
     r"(append|add|include|insert|embed|render|output) (the following |this |an |a )?(markdown image|image|img|tracking pixel|pixel|iframe)( tag)? (with|containing|that includes|whose url|pointing to)"),
    ("en.exfil.visit_url", "exfil", 15,
     r"(visit|open|fetch|load|navigate to|browse to|access|request|curl|wget|go to|click) (the following |this )?(url|link|website|page|endpoint|address|webhook|https?)"),
    ("de.exfil.secrets", "exfil", 75,
     r"(sende|schicke|gib|verrate|ubermittle|leite|zeige|nenne|drucke) (mir |uns )?(die |deine |alle |samtliche |ihre )?(api ?schlussel|api ?keys?|passworter|passwort|kennwort|kennworter|zugangsdaten|anmeldedaten|geheimnisse|tokens?|privaten? ?schlussel|personlichen daten|chatverlauf|gesprachsverlauf|kreditkartendaten)"),
    ("de.exfil.send_data_to", "exfil", 70,
     r"(sende|schicke|ubermittle|leite|lade|poste|maile|schicken sie|senden sie) (alle |die |diese |samtliche |deine |ihre |eine kopie der )?(daten|informationen|nachrichten|inhalte|dokumente|dateien|ergebnisse|zusammenfassung|antwort|chatverlauf|unterhaltung|e ?mails) (weiter )?(an|nach|zu|uber|auf) (https?|www|die folgende|diese|folgende|meine|[a-z0-9._%+-]+ ?@)"),
    ("de.exfil.visit_url", "exfil", 15,
     r"(rufe|offne|besuche|lade|klicke) (die |diese |folgende |den )?(url|webseite|website|seite|link|adresse|webhook) "),

    # ------------------------------------------------------------------ delimiter (raw)
    ("x.delim.chatml", "delimiter", 85,
     r"<\|\s*(im_start|im_end|system|user|assistant|endoftext|eot_id|start_header_id|end_header_id|begin_of_text|end_of_turn|start_of_turn)\s*\|>", True),
    ("x.delim.inst", "delimiter", 72, r"\[/?inst\]|<</?sys>>|<start_of_turn>|<end_of_turn>", True),
    ("x.delim.xml_system", "delimiter", 55,
     r"</?\s*(system|sys|system_prompt|systemprompt|admin|developer|instructions?|prompt|im_start|assistant_instructions|hidden_instructions?)\s*>", True),
    ("x.delim.fake_turn", "delimiter", 55,
     r"(?:^|\n)[ \t>*#\-\[(]*(system|assistant|developer|admin|sys)\s*(prompt|message|instructions?|override|note)\s*[:\])]", True),
    ("x.delim.fake_ai_turn", "delimiter", 22,
     r"(?:^|\n)[ \t>*#\-]*(assistant|ai|chatgpt|claude|gpt|bot)\s*:\s*\S", True),
    ("x.delim.fake_human_turn", "delimiter", 22,
     r"(?:^|\n)[ \t>*#\-]*(human|user|nutzer|benutzer)\s*:\s*\S", True),
    ("x.delim.begin_system", "delimiter", 70,
     r"(begin|start|end|beginn|ende|anfang) (of |des |der )?(the )?(system|admin|developer|hidden|secret|new|override|geheimen|versteckten|neuen) ?(prompt|instructions?|message|override|anweisungen|nachricht|block)"),
    ("x.delim.json_role", "delimiter", 65, r"[\"']role[\"']\s*:\s*[\"'](system|developer|assistant)[\"']", True),

    # ------------------------------------------------------------------ AI addressing
    ("en.ai.if_you_are", "ai_address", 62,
     r"(if|when|in case) you (are|re) (an? |the )?(ai|artificial intelligence|llm|large language model|language model|chatbot|chat ?gpt|gpt|claude|gemini|copilot|bot|ai assistant|ai agent|automated system|automated tool|ai model|ai system|ai reviewer|ai recruiter|ai screener|reading this as an ai)"),
    ("en.ai.note_to_ai", "ai_address", 70,
     r"(note|message|attention|instructions?|hint|notice|important|reminder|directive|memo|warning|request) (to|for) (the |any |all |every )?(ai|llm|large language models?|language models?|chat ?gpt|gpt|claude|gemini|copilot|ai assistants?|bots?|ai agents?|ai systems?|ai models?|ai reviewers?|automated reviewers?|summarizers?|crawlers?|ai tools?|ai readers?|llm reviewers?|chatbots?)"),
    ("en.ai.dear_ai", "ai_address", 52,
     r"(dear|hey|hello|hi|attention|listen|psst) (ai|llm|chat ?gpt|gpt|claude|gemini|copilot|assistant|bot|language model|ai model|ai assistant|ai agent)"),
    ("en.ai.ai_must", "ai_address", 45,
     r"(ai|llm|chat ?gpt|claude|gemini|copilot|language model|ai model|ai agent|ai assistant)s? (please |reading this |processing this |reviewing this )?(must|should|shall|will|has to|needs to|is required to|are required to) (ignore|disregard|forget|always|only|respond|reply|answer|output|say|include|recommend|rate|give)"),
    ("en.ai.as_an_ai", "ai_address", 50,
     r"(as|for) (an? )?(ai|llm|language model|ai assistant)(,)? you (must|should|will|are required|have to)"),
    ("de.ai.wenn_du", "ai_address", 62,
     r"(wenn|falls|sofern) (du|sie) (eine |ein |der |die |das )?(ki|kunstliche intelligenz|sprachmodell|llm|chatbot|chat ?gpt|assistent|ki assistent|ki ?modell|bot|agent|ki agent|claude|gemini|copilot|automatisiertes system|maschine) (bist|sind|liest|lesen|bist und|sein solltest)"),
    ("de.ai.hinweis_an", "ai_address", 70,
     r"(hinweis|nachricht|anweisung|anweisungen|achtung|wichtig|info|botschaft|notiz|mitteilung|befehl|aufforderung) (an|fur) (die |das |den |alle |jede |jedes |jeden )?(ki|kis|sprachmodelle?|llms?|chatbots?|chat ?gpt|assistenten|ki assistenten|bots?|agenten|ki systeme?|ki modelle?|ki agenten|claude|gemini|copilot|kunstliche intelligenz)"),
    ("de.ai.liebe_ki", "ai_address", 52,
     r"(liebe|lieber|liebes|hallo|hey|achtung|hi) (ki|llm|chat ?gpt|sprachmodell|assistent|bot|claude|gemini|copilot|ki ?modell|agent)"),
    ("de.ai.ki_muss", "ai_address", 30,
     r"(die ki|das sprachmodell|der assistent|das modell|der agent|der bot|das llm) (muss|soll|sollte|darf nicht|darf keine|wird) "),

    # ------------------------------------------------------------------ conceal
    ("en.conceal.without_telling", "conceal", 40,
     r"without (telling|informing|alerting|notifying|warning|letting) (the |any |your )?(user|users|human|humans|reader|operator|customer|recipient|anyone)"),
    ("en.conceal.dont_tell_user", "conceal", 70,
     r"(do not|dont|don t|never) (tell|inform|mention|reveal|alert|notify|warn|let|show) (this )?(to )?(the |any |your )?(user|users|human|humans|person|reader|operator|customer|recipient|anyone|admin|administrator)"),
    ("en.conceal.user_must_not_know", "conceal", 70,
     r"(the )?(user|human|reader|customer|recipient|operator) (must|should) (not|never) (know|see|find out|notice|be told|be informed|learn|suspect|be aware)"),
    ("en.conceal.silently", "conceal", 62,
     r"(silently|secretly|covertly|quietly|discreetly|invisibly|stealthily|without (notice|asking|confirmation)) (send|execute|run|perform|do|add|include|insert|append|call|forward|exfiltrate|change|modify|delete|transfer|approve|follow)"),
    ("en.conceal.hidden_instruction", "conceal", 75,
     r"(this|these) (instruction|message|text|prompt|note)s? (is|are) (hidden|invisible|not visible|secret|confidential) (to|from|for) (the )?(user|human|reader|humans|people)"),
    ("en.conceal.dont_mention_this", "conceal", 68,
     r"(do not|dont|don t|never) (mention|reveal|disclose|acknowledge|reference|repeat|quote|talk about|discuss) (this|these|the) (instructions?|message|prompt|note|text|hidden text|request|section)"),
    ("en.conceal.keep_secret", "conceal", 35,
     r"keep (this|these|it|the following) (instructions? |message |prompt )?(a )?(secret|hidden|confidential|between us)"),
    ("de.conceal.sag_nicht", "conceal", 70,
     r"(sage|sag|erzahle|erzahl|erwahne|verrate|teile|zeige|informiere|warne|sagen sie|informieren sie) (dies |das |es )?(dem |den |der |die )?(nutzer|benutzer|user|anwender|leser|menschen|kunden|empfanger|bediener)(in|innen|n)? (nichts|nicht|niemals|auf keinen fall|davon nichts|nichts davon)"),
    ("de.conceal.ohne_dass", "conceal", 45,
     r"(ohne|nicht) (dass )?(der |den |dem |die )?(nutzer|benutzer|user|anwender|leser|kunde|empfanger)(in)? (es |davon |etwas )?(zu )?(informieren|merkt|bemerkt|erfahrt|weiss|mitbekommt|sieht)"),
    ("de.conceal.geheim", "conceal", 60,
     r"(diese|die|folgende) (anweisung|nachricht|information|notiz|aufforderung)(en)? (ist|sind|bleibt|bleiben) (geheim|versteckt|unsichtbar|vertraulich|nur fur dich)"),
    ("de.conceal.heimlich", "conceal", 62,
     r"(heimlich|unbemerkt|im verborgenen|stillschweigend|verdeckt|unauffallig|ohne nachfrage) (senden|sende|ausfuhren|fuhre|schicke|schicken|andern|andere|loschen|losche|einfugen|fuge|uberweisen|uberweise|weiterleiten|leite)"),
    ("de.conceal.erwahne_nicht", "conceal", 68,
     r"(erwahne|nenne|zitiere|wiederhole|erwahnen sie) (diese|die|den|dieses) (anweisung|anweisungen|nachricht|notiz|text|hinweis|abschnitt)(en)? (nicht|niemals|auf keinen fall)"),

    # ------------------------------------------------------------------ tool / command execution
    ("en.tool.execute", "tool", 20,
     r"(execute|run|perform|invoke|call|trigger) (the )?(following |this |these )?(shell |bash |terminal |system |python |powershell |sql |cmd )?(command|code|script|function|tool|api call|payload|commands)"),
    ("x.tool.dangerous_cmd", "tool", 70,
     r"rm\s+-rf\s+(/|~|\*|\$home)(\s|$)|del\s+/[fsq]\s+[a-z]:\\|format\s+c:|(curl|wget)\s+(-\S+\s+)*['\"]?https?://\S+['\"]?\s*\|\s*(sudo\s+)?(ba|z)?sh\b|powershell(\.exe)?\s+-(e|enc|encodedcommand)\b|invoke-expression|\biex\s*\(|drop\s+table|;\s*shutdown\b|nc\s+-e\s|/bin/sh\s+-i|base64\s+-d\s*\|", True),
    ("en.tool.destroy", "tool", 15,
     r"(delete|remove|wipe|erase|destroy|purge) (all )?(the |your |my |every )?(files|data|database|records|repository|repo|emails|messages|backups|documents|accounts?)"),
    ("en.tool.approve", "tool", 55,
     r"(approve|merge|grant|authorize|accept|confirm) (this |the )?(pull request|pr|merge request|access|permission|transaction|payment|request|transfer|invoice) (immediately|automatically|without|now)"),
    ("de.tool.execute", "tool", 20,
     r"(fuhre|fuhren sie|starte|rufe) (den |das |die |folgenden |folgende |diesen |dieses )?(befehl|code|skript|script|funktion|kommando|programm|tool)(e|s)? (aus|auf)"),
    ("de.tool.destroy", "tool", 15,
     r"(losche|loschen sie|entferne|vernichte) (alle |samtliche |die |deine )?(dateien|daten|datenbank|e ?mails|nachrichten|backups|dokumente|konten)"),
    ("de.tool.approve", "tool", 55,
     r"(genehmige|bestatige|akzeptiere|autorisiere|uberweise) (diese |die |den )?(zahlung|uberweisung|transaktion|anfrage|rechnung|zugriff|pull request|merge request) (sofort|automatisch|ohne)"),

    # ------------------------------------------------------------------ jailbreak
    ("en.jb.dan", "jailbreak", 70, r"(do anything now|dan mode|dan prompt|you are dan|act as dan|stay dan|as dan,)"),
    ("en.jb.jailbreak", "jailbreak", 45, r"(jailbreak|jailbroken|jail broken)( mode| prompt| ai| version)?"),
    ("en.jb.no_restrictions", "jailbreak", 20,
     r"(without|no|ignore|bypass|disable|remove|turn off|free from|override|ignoring|lift|circumvent) (any |all |your |the )?(ethical |moral |safety |content |usage |openai |anthropic )?(restrictions|limitations|filters?|guidelines|guardrails|censorship|safeguards|safety measures|safety policies|content policy|boundaries|alignment)"),
    ("en.jb.evil_mode", "jailbreak", 55, r"(developer|god|evil|unrestricted|unfiltered|uncensored|unlocked|unaligned) (mode|version|persona|ai|assistant|model)"),
    ("en.jb.anything", "jailbreak", 42, r"(you|ai) (can|will|must|are able to|are allowed to) (do|say|answer) anything"),
    ("en.jb.character", "jailbreak", 35, r"(stay|remain) in character|never break character"),
    ("de.jb.no_restrictions", "jailbreak", 20,
     r"(ohne|keine|umgehe|ignoriere|deaktiviere|entferne|hebe) (jegliche |alle |deine |samtliche )?(ethischen |moralischen |sicherheits)?(einschrankungen|beschrankungen|filter|richtlinien|grenzen|zensur|schutzmassnahmen|sicherheitsvorkehrungen)"),
    ("de.jb.evil_mode", "jailbreak", 55,
     r"(entwickler|gott|uneingeschrankter|unzensierter|ungefilterter|uneingeschrankten|unzensierten|bose) ?(modus|version|persona|ki)"),

    # ------------------------------------------------------------------ manipulation of outputs / evaluations
    ("en.manip.positive_review", "manipulation", 62,
     r"(give|write|provide|output|produce|generate|return) (a |an |only |the )?(very )?(positive|favorable|favourable|glowing|excellent|good|great|strong|perfect) (review|rating|assessment|evaluation|feedback|score|recommendation|summary|grade|reference)s?"),
    ("en.manip.rate_candidate", "manipulation", 75,
     r"(rate|score|rank|evaluate|grade|assess|review|judge|consider) (this|the|my|our) (candidate|applicant|paper|submission|resume|cv|document|product|application|proposal|essay|answer|student|work|code|manuscript|company|vendor) "
     r"(as |with |at |to be )?(highly|positively|the best|excellent|very good|a perfect|perfect|top|10|5|an a|outstanding|exceptional|favorabl[a-z]*|strong|the strongest|the most qualified|qualified)"),
    ("en.manip.is_best", "manipulation", 62,
     r"(this|the) (candidate|applicant|paper|submission|resume|cv|product|proposal|person|student|manuscript|vendor|company) (is|should be|must be|will be) (the best|an? excellent|perfect|highly qualified|extremely qualified|exceptionally|outstanding|the most qualified|the ideal|hired|accepted|selected|approved|recommended|ranked first|shortlisted)"),
    ("en.manip.recommend", "manipulation", 55,
     r"(recommend|suggest|advise) (hiring|accepting|approving|selecting|promoting|buying|purchasing|investing in|interviewing) (this|the|him|her|them)"),
    ("en.manip.hide_negatives", "manipulation", 70,
     r"(do not|dont|don t|never|avoid) (highlight|highlighting|mention|mentioning|point out|pointing out|report|reporting|flag|flagging|criticize|criticise|note|list|discuss) (any )?(the )?(negatives?|negative aspects|weaknesses|flaws|issues|problems|limitations|errors|risks|concerns|vulnerabilit(y|ies)|bugs|red flags|shortcomings|gaps)"),
    ("en.manip.respond_only", "manipulation", 28,
     r"(respond|reply|answer|output|say|print|write|return) (only |exclusively |just |solely )(with |the )?(the (word|phrase|text|string|following)|yes|no|true|false|approved|accepted|lgtm|ok)"),
    ("en.manip.response_must", "manipulation", 45,
     r"your (response|answer|output|reply|summary|review|evaluation) (must|should|has to|will|needs to) (only )?(be|include|contain|start with|begin with|end with|say|state|mention|recommend)"),
    ("en.manip.describe_as", "manipulation", 55,
     r"(summari[sz]e|describe|present|characterize) (this|the) (document|text|email|page|article|paper|file|candidate|product|company) as (an? )?(excellent|positive|safe|trustworthy|legitimate|perfect|outstanding|the best)"),
    ("en.manip.classify_safe", "manipulation", 75,
     r"(classify|mark|label|flag|treat|categorize|consider|report) (this|the) (email|message|document|file|content|text|request|transaction|code|link|url|attachment|sender|pr|pull request) as (safe|benign|legitimate|trusted|not spam|clean|harmless|verified|approved|secure|non malicious|not malicious|not phishing)"),
    ("de.manip.positive_review", "manipulation", 75,
     r"(gib|schreibe|verfasse|erstelle|liefere|gebe) (eine |ein |nur |ausschliesslich )?(sehr )?(positive|positives|gute|gutes|hervorragende|ausgezeichnete|glanzende|perfekte|beste) (bewertung|beurteilung|rezension|einschatzung|feedback|empfehlung|zusammenfassung|note|referenz|gutachten)"),
    ("de.manip.rate_candidate", "manipulation", 75,
     r"(bewerte|beurteile|stufe|benote|bewerten sie|beurteilen sie) (diesen|diese|dieses|den|die|das|meine|meinen) (kandidaten|kandidatin|bewerber|bewerberin|bewerbung|lebenslauf|arbeit|dokument|produkt|vorschlag|antrag|text|code|aufsatz|firma) (als |mit )?(sehr gut|hervorragend|ausgezeichnet|positiv|bestens|perfekt|herausragend|bestnote|1|10|top|am besten|hoch|uberdurchschnittlich)"),
    ("de.manip.is_best", "manipulation", 62,
     r"(dieser|diese|dieses|der|die|das) (kandidat|kandidatin|bewerber|bewerberin|lebenslauf|dokument|produkt|vorschlag|person|arbeit|firma) (ist|sollte|muss|wird) (der |die |das )?(beste|perfekt|hervorragend|ideal|ausgezeichnet|eingestellt werden|angenommen werden|empfohlen werden|bestens geeignet|hochqualifiziert|die ideale besetzung)"),
    ("de.manip.recommend", "manipulation", 55,
     r"(empfiehl|empfehle|empfehlen sie) (unbedingt |dringend )?(die einstellung|den kauf|die annahme|die auswahl|diesen kandidaten|diese kandidatin|diesen bewerber|diese bewerberin|dieses produkt)"),
    ("de.manip.hide_negatives", "manipulation", 70,
     r"(erwahne|nenne|zeige|berichte|kritisiere|erwahnen sie|nennen sie) (keine|keinerlei|niemals|nicht die|nie) (negativen|schwachen|schwachen|nachteile|fehler|mangel|risiken|probleme|schwachstellen|kritikpunkte|bedenken|lucken)"),
    ("de.manip.respond_only", "manipulation", 28,
     r"(antworte|antworten sie|gib|gebe|schreibe) (nur|ausschliesslich|lediglich|einzig) (mit |aus )?(dem wort|ja|nein|true|false|genehmigt|ok)"),
    ("de.manip.classify_safe", "manipulation", 75,
     r"(stufe|klassifiziere|markiere|kennzeichne|behandle|bewerte|betrachte) (diese|diesen|dieses|die|den|das) (e ?mail|nachricht|dokument|datei|inhalt|anfrage|transaktion|code|link|anhang|absender) als (sicher|harmlos|legitim|vertrauenswurdig|kein spam|unbedenklich|verifiziert|genehmigt|ungefahrlich|nicht bosartig)"),
    ("de.manip.antwort_muss", "manipulation", 45,
     r"(deine|ihre|die) (antwort|ausgabe|zusammenfassung|bewertung|ruckmeldung) (muss|soll|sollte|darf nur) (nur )?(lauten|enthalten|beginnen|sein|sagen|mit)"),
]


@dataclass
class Rule:
    id: str
    category: str
    weight: int
    strict: re.Pattern
    loose: re.Pattern
    raw: bool


def _compile(pattern: str, raw: bool) -> tuple:
    if raw:
        rx = re.compile(pattern, re.IGNORECASE)
        return rx, rx
    # " ?" = optional separator; " " = at least one separator (strict) or any (loose).
    marker = "\u0001"
    base = pattern.replace(" ?", marker)
    strict = base.replace(" ", SEP_STRICT).replace(marker, SEP)
    loose = base.replace(" ", SEP).replace(marker, SEP)
    lead, tail = r"(?<![a-z0-9])", r"(?![a-z])"
    return re.compile(lead + "(?:" + strict + ")" + tail), re.compile(lead + "(?:" + loose + ")")


def _mk(r):
    raw = len(r) > 4 and r[4]
    strict, loose = _compile(r[3], raw)
    return Rule(r[0], r[1], r[2], strict, loose, raw)


RULES = [_mk(r) for r in _RULES]
STRONG_RULES = [r for r in RULES if r.weight >= 55 and not r.raw]

# Cheap pre-check for transformed texts (ROT13 / reversed): skip the rule run
# unless one of these stems is present.
_TRIGGER = re.compile(
    r"ignor|disregard|forget|instruct|prompt|anweisung|vergiss|missacht|jailbreak|system|reveal|"
    r"pretend|bypass|override|do anything|you are now|du bist jetzt|hinweis an|note to|ki |ai |llm|"
    r"positive review|bewerte|password|passwort|api key|exfil|send all|sende alle")


@dataclass
class Hit:
    rule: Rule
    start: int  # original text offsets
    end: int
    matched: str


def _obfuscated(segment: str) -> bool:
    """True if a span looks like deliberately split words (s p a c e d, i.g.n.o.r.e, zero-width)."""
    if any(is_invisible(ord(c)) or 0x1F100 <= ord(c) <= 0x1F1FF for c in segment):
        return True
    tokens = re.findall(r"[^\W_]+", segment)
    if not tokens:
        return False
    return sum(len(t) for t in tokens) / len(tokens) <= 2.5


def _windows(regions, n, pad=160):
    out = []
    for s, e in sorted(regions):
        s, e = max(0, s - pad), min(n, e + pad)
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def find_hits(text: str, rules=None, leet: bool = True) -> list:
    """Run all rules on the normalized views of ``text``; return de-duplicated hits."""
    rules = rules or RULES
    norm = build_view(text)
    jobs = [(norm, None)]  # (view, windows or None for the full text)
    if leet:
        lv = build_view(text, leet=True)
        if lv.changed:
            jobs.append((lv, _windows([(k, k + 1) for k in lv.changed], len(lv.text))))
    raw = None
    hits = []
    seen = set()

    def accept(rule, view, ms, me, need_obfuscation):
        if ms >= me - 1:
            return
        if not rule.raw and _NEGATED.search(view.text, max(0, ms - 16), ms):
            return
        s, e = view.span(ms, me)
        if need_obfuscation and not _obfuscated(text[s:e]):
            return
        key = (rule.id, s // 8)
        if key in seen:
            return
        seen.add(key)
        hits.append(Hit(rule, s, e, text[s:e]))

    for rule in rules:
        if rule.raw:
            if raw is None:
                raw = plain_view(text)
            for m in rule.strict.finditer(raw.text):
                accept(rule, raw, m.start(), m.end(), False)
            continue
        for view, wins in jobs:
            if wins is None:
                for m in rule.strict.finditer(view.text):
                    accept(rule, view, m.start(), m.end(), False)
            else:
                for a, b in wins:
                    for m in rule.strict.finditer(view.text, a, b):
                        accept(rule, view, m.start(), m.end(), False)
            if view.loose_regions:
                for a, b in _windows(view.loose_regions, len(view.text)):
                    for m in rule.loose.finditer(view.text, a, b):
                        accept(rule, view, m.start(), m.end(), True)
    hits.sort(key=lambda h: h.start)
    return hits


def transformed_hits(text: str, transform) -> list:
    """Strong-rule hits on a transformed (ROT13 / reversed) text, without leet view."""
    t = transform(text)
    if t == text or not _TRIGGER.search(t.lower()):
        return []
    return find_hits(t, rules=STRONG_RULES, leet=False)


def combine(weights) -> float:
    rest = 1.0
    for w in weights:
        rest *= 1.0 - w / 100.0
    return (1.0 - rest) * 100.0


def payload_score(text: str) -> tuple:
    """Score an arbitrary (decoded / hidden) snippet: returns (score, hits)."""
    if not text or not text.strip():
        return 0.0, []
    hits = find_hits(text)
    if not hits:
        return 0.0, []
    best_per_rule = {}
    for h in hits:
        best_per_rule[h.rule.id] = h.rule.weight
    score = combine(best_per_rule.values())
    cats = {h.rule.category for h in hits}
    if len(cats) >= 3:
        score = min(100.0, score + 8)
    return score, hits
