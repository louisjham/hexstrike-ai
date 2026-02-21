import awesome_skills

def test():
    print("Testing get_skills_by_category()...")
    cats = awesome_skills.get_skills_by_category()
    print(f"Total categories loaded: {len(cats)}")
    
    for cat, skills in sorted(cats.items()):
        print(f"[{cat}] - {len(skills)} skills")
        
    print("\nSample from 'game-development':")
    for s in cats.get("game-development", [])[:3]:
        print(f"  - @{s['name']}")

if __name__ == "__main__":
    test()
