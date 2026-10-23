# JanMat

**Understand India's new laws in plain language, and see what people are saying about them.**

Live app: https://jan-mat-new.vercel.app

---

## What is JanMat?

When the government proposes a new law, it is usually a long, difficult document. Most people never read it, and most people never find out what others think of it.

JanMat fixes both problems:

1. **Ask a question, get a clear answer.** Type (or speak) something like *"What does this bill change for small businesses?"* JanMat answers in simple words and shows you exactly which documents it used, so you can check it yourself.
2. **See what everyone is saying.** Every bill has a public comment section. Anyone can read the comments without signing up. If you want to add your own, create a free account.

If JanMat does not have the answer, it tells you so. It never makes things up.

---

## Who is it for?

- **Citizens and students** who want to understand a law without a law degree.
- **Journalists and NGOs** who need to follow bills and public reaction.
- **Businesses and law firms** who need to track what is being proposed and who is objecting.

---

## How to use it

1. Open the website.
2. Type a question in the chat box, or press the microphone and speak.
3. Read the answer. The sources it used are listed underneath.
4. Scroll down to read public comments on any bill. Sign in to post your own.

---

## The big idea: TinyFish keeps JanMat connected to the live internet

A law-explainer is only useful if it knows about **today's** laws and **today's** discussion. That information is spread across hundreds of websites, and many of those sites are hard for a computer to read: they block automated visitors, hide content behind scripts, or show comments in a different layout every time.

This is where **TinyFish** comes in. TinyFish is a service that lets software use the live web the way a person would. JanMat uses it in three ways:

### 1. Finding new material (TinyFish Search)
Instead of relying on a fixed list of websites, JanMat asks TinyFish to search the web for new draft bills, government consultation notices and public reactions. When something new is published, JanMat can pick it up and learn from it.

### 2. Opening pages that normally refuse to open (TinyFish Fetch)
Some government and organisation websites turn away automated visitors, or fail to load. When JanMat hits one of these, it hands the page to TinyFish, which opens it like a real browser and hands back clean text. Without this, those documents would simply be missing from the answers.

### 3. Reading people's comments off any website (TinyFish Web Agent)
This is the most important one. Public comments appear on many different websites, each laid out differently, so there is no single "comment button" to copy from. JanMat gives TinyFish a simple instruction in plain English: *"Find every public comment on this page and tell me who wrote it."* TinyFish opens the page, finds the comments, and returns them neatly organised. JanMat then makes them searchable, so you can ask *"What are industry groups saying about this bill?"* and get a real answer.

**In short:** TinyFish is how JanMat finds, opens and reads the live web. Without it, JanMat would only know what was easy to copy.

The Web Agent is told to only read what any visitor can see. It never logs in, submits forms or posts anything.

---

## Behind the scenes (in simple terms)

1. **Collect:** JanMat gathers bills and related documents, using TinyFish for the hard-to-reach ones.
2. **Store:** Each document is cut into small pieces and saved in a searchable library.
3. **Answer:** When you ask a question, JanMat finds the pieces most related to it and writes an answer using only those, then lists them as sources.

The comment section and accounts are handled separately, so reading is open to everyone while posting needs a login.


---

## Built with

TinyFish (live web), Groq (writes the answers), Sarvam (voice), Supabase (database and login), Hugging Face (the engine), Vercel (the website).

Bill texts and commentary come from [PRS Legislative Research](https://prsindia.org), used with acknowledgement.

*For setup instructions and technical details, see `README.md` and `DEPLOY.md`.*
