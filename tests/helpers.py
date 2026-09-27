from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def atom(serial=1, name="CA", res=1, chain="A", xyz=(0., 0., 0.), *, icode="", alt="", element="C", residue="GLY", occupancy=1.):
    return (f"ATOM  {serial:5d} {name:>4s}{alt:1s}{residue:>3s} {chain:1s}{res:4d}{icode:1s}   "
            f"{xyz[0]:8.3f}{xyz[1]:8.3f}{xyz[2]:8.3f}{occupancy:6.2f}{20.:6.2f}          {element:>2s}  \n")


def backbone(res=1, chain="A", offset=0., icode="", skip=()):
    return "".join(atom(i+1, n, res, chain, (offset+x, y, 0), icode=icode, element=e)
                   for i,(n,x,y,e) in enumerate([("N",0,0,"N"),("CA",1.4,0,"C"),("C",2.3,1,"C"),("O",2.2,2.2,"O")]) if n not in skip)
