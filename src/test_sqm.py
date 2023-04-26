

def main():
   s = 10
   while s<21.5:
      s= s + 0.1
      e = 0
      if s <= 11:
         e = 0
      elif s >11 and s <= 12:
         e= 0.04
      elif s > 12 and s <= 13:
         e = 0.07
      elif s > 13 and s <= 14:
         e = 0.20
      elif s > 14 and s <= 15:
         e = 0.70
      elif s > 15 and s <= 16:
         e = 1.00
      elif s > 16 and s <= 17:
         e = 1.75
      elif s > 17 and s <= 18:
         e = 3.00
      elif s > 18 and s <= 19:
         e = 15
      elif s > 19 and s <= 20:
         e = 30
      elif s > 20  and s <= 21:
         e = 45
      elif s > 20  and s <= 22:
         e = 75
      else:
         e= 0
      
      ec = float(0)
      if s > 10.5:
         ec = round((2.84**s/((s**2)*80000)),4) 
      
      if ec > 55:
         ec = 55

      print ("SQM: " + str(round(s,2))+ ": "  + str(round(e,3)) + " , " + str(round(ec,3)))
   return 

if __name__ == "__main__":
   main()


