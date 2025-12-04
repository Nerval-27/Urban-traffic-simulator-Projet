open Type

let () =
  print_endline "=== Traffic Simulator ===";


  let json_path =
    Filename.concat (Sys.getcwd ()) "data/map_clean.json"
  in

  Printf.printf "Chargement du fichier : %s\n" json_path;

  let network =
    try Jsonloader.load_network json_path
    with exn ->
      Printf.printf "Erreur réelle : %s\n" (Printexc.to_string exn);
      failwith "Chargement JSON échoué"
  
  in
    
  Printf.printf "✔ Réseau chargé : %d routes\n"
    (List.length network.roads);


  print_endline "Initialisation des véhicules (non implémentée)...";

  (* 3. Boucle de simulation — squelette vide *)
  let steps = 10 in
  for t = 0 to steps do
    Printf.printf "Tick %d...\n" t;
    (* plus tard : update positions, collisions, lights, etc. *)
  done;

  print_endline "Simulation terminée."
