Full closet, but still don't know what to wear? 👗🤔

That's why we built DressMe, an AI-powered application that helps you choose outfits, organize your wardrobe, pack for trips, and avoid buying clothes you already own. 🛍️

🎯 Our goal: make everyday clothing decisions easier by helping users get the most out of their existing wardrobe.

⚙️ How does it work?
We developed a multi-agent AI system using LangGraph, where specialized agents collaborate to handle different tasks. LLMs understand user requests and explain recommendations, while dedicated tools verify information and perform calculations.

🔑 Key technologies behind DressMe:

📚 RAG (Retrieval-Augmented Generation): personalized styling advice using knowledge from 38 fashion books, combined with real wardrobe data.

👁️ Computer Vision (YOLO + GPT-4o Vision): a YOLO detector finds and segments each garment and measures its colors on the pixels, then GPT-4o Vision refines category, material, season and occasion as strict JSON. The same detector powers Live Scan and "Should I buy this?".

📊 Machine Learning (XGBoost + FashionCLIP): identifies wardrobe gaps, detects similar items, and helps avoid unnecessary purchases.

🧳 Optimization (OR-Tools CP-SAT): builds packing recommendations based on trip requirements and wardrobe constraints.

🧍 3D Avatar & Virtual Try-On (Hunyuan3D + FASHN): visualize clothes on a 3D avatar before choosing an outfit.

🔗 Agent Communication (A2A Protocol): specialized agents exchange information and coordinate tasks through a shared wardrobe system.

🛠️ Built with React, FastAPI, LangGraph and Supabase, bringing AI, machine learning, computer vision and optimization into one platform.

✨ The idea is simple: choose better outfits, pack smarter, and shop more thoughtfully.

🙏 A big thank you to my teammates for this great collaboration!
@Mariem Gharbi @Zied Heshmi @Mohamed Mahmoud @Mariem Ben Abdallah @Nourhene Mraieh

#ArtificialIntelligence #AI #MultiAgentSystems #LangGraph #MachineLearning #YOLO #ComputerVision #RAG #XGBoost #LLM #GenerativeAI #FastAPI #React #Optimization #FashionTech
