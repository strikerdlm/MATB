declare module "proj4" {
  type Coordinate = [number, number];
  interface Proj4 {
    (source: string, target: string, coordinate: Coordinate): Coordinate;
  }
  const proj4: Proj4;
  export default proj4;
}

declare module "mgrs" {
  interface MgrsApi {
    forward(coordinate: [number, number], accuracy?: number): string;
    toPoint(value: string): [number, number];
  }
  const mgrs: MgrsApi;
  export default mgrs;
}
