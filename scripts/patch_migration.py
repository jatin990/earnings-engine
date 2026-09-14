"""Patch migration 042 itinerary: replace bungee-on-day-1 with bungee-on-day-11, remove flood warnings."""
import re

PATH = "D:/earnings-engine/earnings_engine/data/migrations.py"

with open(PATH, "r", encoding="utf-8") as f:
    content = f.read()

# Find the start of the old itinerary_rows = [ line
start_marker = "    # 5. Seed 11-day itinerary"
end_marker = "    # 6. Seed 3 trip activities"

start_idx = content.index(start_marker)
end_idx = content.index(end_marker)

old_block = content[start_idx:end_idx]
print(f"Found old itinerary block: {len(old_block)} chars, lines ~{content[:start_idx].count(chr(10))+1}-{content[:end_idx].count(chr(10))+1}")

new_block = '''    # 5. Seed 11-day itinerary — bungee on last day, no flood warnings
    itinerary_rows = [
        ("itin_abc_d01", "trip_nepal_abc_2026", 1, "2026-10-01",
         "Arrive Pokhara & Acclimatise",
         "Fly into Pokhara via Kathmandu. Check into hotel, rest and acclimatise. "
         "Evening stroll along Phewa Lakeside. Gear check and trek briefing.",
         "Pokhara Airport (820m)", "Pokhara (820m)",
         820, 0.0, None, "Hotel Butterfly, Pokhara", "B/D", "Rest", None),
        ("itin_abc_d02", "trip_nepal_abc_2026", 2, "2026-10-02",
         "Drive to Nayapul -> Trek to Tikhedhunga",
         "Drive from Pokhara to Nayapul (~2h). Begin the ABC trail through Birethanti village. "
         "Gradual walk along the Modi Khola river valley to Tikhedhunga.",
         "Pokhara (820m)", "Tikhedhunga (1540m)",
         1540, 12.0, 5.0, "Teahouse, Tikhedhunga", "B/L/D", "Moderate", None),
        ("itin_abc_d03", "trip_nepal_abc_2026", 3, "2026-10-03",
         "Tikhedhunga -> Ghorepani via Ulleri",
         "Steep ascent via the famous 3,300 stone steps through Ulleri village. "
         "Trek through rhododendron and oak forest. Arrive Ghorepani with panoramic "
         "Annapurna South and Dhaulagiri views.",
         "Tikhedhunga (1540m)", "Ghorepani (2860m)",
         2860, 9.0, 6.0, "Teahouse, Ghorepani", "B/L/D", "Hard", None),
        ("itin_abc_d04", "trip_nepal_abc_2026", 4, "2026-10-04",
         "Poon Hill Sunrise (4am) -> Trek to Tadapani",
         "Pre-dawn 4am hike to Poon Hill (3210m) for 360 sunrise panorama: Annapurna I, "
         "Dhaulagiri, Machhapuchhre (Fish Tail). Descend through rhododendron forest to Tadapani.",
         "Ghorepani (2860m) -> Poon Hill (3210m)", "Tadapani (2630m)",
         2630, 11.0, 7.0, "Teahouse, Tadapani", "B/L/D", "Moderate", None),
        ("itin_abc_d05", "trip_nepal_abc_2026", 5, "2026-10-05",
         "Tadapani -> Chhomrong",
         "Descend through dense forest to the terraced village of Chhomrong, the last major "
         "settlement before entering the Annapurna Sanctuary. Stunning views of Annapurna "
         "South and Machhapuchhre.",
         "Tadapani (2630m)", "Chhomrong (2170m)",
         2170, 8.0, 5.0, "Teahouse, Chhomrong", "B/L/D", "Moderate", None),
        ("itin_abc_d06", "trip_nepal_abc_2026", 6, "2026-10-06",
         "Chhomrong -> Bamboo (via Sinuwa)",
         "Descend from Chhomrong stone steps to Sinuwa village, then continue into the "
         "Annapurna Sanctuary through dense bamboo and rhododendron forest. The upper trail "
         "via Sinuwa is the current standard route.",
         "Chhomrong (2170m)", "Bamboo (2310m)",
         2310, 10.0, 6.0, "Teahouse, Bamboo", "B/L/D", "Hard", None),
        ("itin_abc_d07", "trip_nepal_abc_2026", 7, "2026-10-07",
         "Bamboo -> Deurali (via Himalaya Hotel)",
         "Trek deeper into the Modi Khola gorge. Pass through Dobhan and Himalaya Hotel. "
         "The trail narrows between towering canyon walls. Look for Himalayan tahr and "
         "waterfalls above Himalaya Hotel.",
         "Bamboo (2310m)", "Deurali (3230m)",
         3230, 8.0, 5.0, "Teahouse, Deurali", "B/L/D", "Hard", None),
        ("itin_abc_d08", "trip_nepal_abc_2026", 8, "2026-10-08",
         "Deurali -> Annapurna Base Camp",
         "Final ascent into the Annapurna Sanctuary. Pass Machhapuchhre Base Camp (MBC, 3700m) "
         "with Fish Tail peak towering overhead. Arrive at ABC (4130m) surrounded by "
         "Annapurna I (8091m), Annapurna South, Gangapurna, and Machhapuchhre. Golden hour photography.",
         "Deurali (3230m)", "Annapurna Base Camp (4130m)",
         4130, 8.0, 5.0, "ABC Camp teahouse (4130m)", "B/L/D", "Hard", None),
        ("itin_abc_d09", "trip_nepal_abc_2026", 9, "2026-10-09",
         "ABC -> Bamboo (Descent)",
         "Descend from the sanctuary back through MBC, Deurali, Himalaya Hotel, Dobhan to Bamboo. "
         "Faster going down, the altitude drop is significant (4130m to 2310m) so take care on knees.",
         "Annapurna Base Camp (4130m)", "Bamboo (2310m)",
         2310, 14.0, 7.0, "Teahouse, Bamboo", "B/L/D", "Moderate", None),
        ("itin_abc_d10", "trip_nepal_abc_2026", 10, "2026-10-10",
         "Bamboo -> Nayapul -> Pokhara",
         "Final trekking day. Descend through Sinuwa, Chhomrong, and back to Nayapul. "
         "Drive from Nayapul to Pokhara (~2h). Hot shower, lakeside celebration dinner!",
         "Bamboo (2310m)", "Pokhara (820m)",
         820, 22.0, 9.0, "Hotel Butterfly, Pokhara", "B/L/D", "Easy", None),
        ("itin_abc_d11", "trip_nepal_abc_2026", 11, "2026-10-11",
         "Kushma Bungee Jump (228m) - Worlds Highest",
         "Early morning drive from Pokhara to Kushma (~3h, Parbat District). "
         "Jump from the 228m suspension bridge, the worlds highest bungee jump, "
         "over the Bhote Koshi river gorge. Return to Pokhara by evening. Departure or extra night.",
         "Kushma, Parbat District (228m bungee)", "Pokhara (820m)",
         820, 180.0, None, "Hotel Butterfly, Pokhara", "B/L/D", "Easy",
         "Optional: rafting on the Trisuli River en route to Kushma."),
    ]

'''

new_content = content[:start_idx] + new_block + content[end_idx:]

with open(PATH, "w", encoding="utf-8") as f:
    f.write(new_content)

print("Migration 042 itinerary updated: bungee moved to Day 11, flood warnings removed.")
