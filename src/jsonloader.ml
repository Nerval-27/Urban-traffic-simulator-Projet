
open Yojson.Basic.Util
open Type

(* Convertit un champ JSON en int64 même si la valeur est très grande ou null *)
let parse_int64 json =
  match json with
  | `Int i -> Int64.of_int i
  | `String s -> Int64.of_string s   (* si jamais un ID est stocké comme string *)
  | `Null -> Int64.minus_one
  | _ ->
      failwith ("Expected int64-compatible JSON, got " ^
                Yojson.Basic.to_string json)

(* Convertit une liste JSON de node_id en list int64 *)
let parse_node_id_list json =
  json
  |> to_list
  |> List.filter_map (fun x ->
        match x with
        | `Null -> None
        | `Int _ | `String _ -> Some (parse_int64 x)
        | _ ->
            failwith ("Invalid node type: " ^ Yojson.Basic.to_string x)
     )

(* Conversion d’une route depuis le JSON *)
let parse_road json =
  {
    id = json |> member "id" |> to_int;
    length = json |> member "length" |> to_float;
    speed_limit = json |> member "speed_limit" |> to_float;

    nodes = json |> member "nodes" |> parse_node_id_list;

    (* next peut être int, string ou null *)
    next = json |> member "next" |> parse_int64;
  }

(* Chargement du réseau complet *)
let load_network filename =
  let json = Yojson.Basic.from_file filename in
  let roads_json = json |> member "roads" |> to_list in
  let roads = List.map parse_road roads_json in
  {
    roads = roads;
    intersections = [];
  }
